#!/usr/bin/env python3
"""
cert-and-stapling-monitor.py

Monitor TLS certificate validity, chain completeness, SAN coverage,
and OCSP stapling status across a hostname inventory. The checks
match the failure modes Chapter 13 of SEO for Engineers, Volume 1,
identifies as the highest-risk production HTTPS problems.

Checks performed.

  1. Certificate expiry window, with configurable warning thresholds.
  2. SAN hostname coverage, accounting for single-label wildcards.
  3. Chain completeness, no reliance on local intermediate caches.
  4. OCSP stapling status (warning, the script does not enforce
     stapling; it reports whether it is active).
  5. Must-Staple extension presence, flagging hostnames with
     Must-Staple certificates where stapling is not working.
  6. Maximum-validity-period check against the CA/B Forum
     SC-081v3 schedule.

Usage:
    python cert-and-stapling-monitor.py --host example.com
    python cert-and-stapling-monitor.py --hosts-file hosts.txt
    python cert-and-stapling-monitor.py --hosts-file hosts.txt \\
      --warn-days 21 --error-days 5
    python cert-and-stapling-monitor.py --hosts-file hosts.txt \\
      --output report.json

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 13.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import TLSFeature, TLSFeatureType
from cryptography.x509.oid import ExtensionOID, NameOID

# CA/Browser Forum SC-081v3 maximum validity schedule (UTC dates).
VALIDITY_SCHEDULE = [
    (datetime(2026, 3, 15, tzinfo=timezone.utc), 398),  # before this date
    (datetime(2027, 3, 15, tzinfo=timezone.utc), 200),
    (datetime(2029, 3, 15, tzinfo=timezone.utc), 100),
    (datetime(9999, 12, 31, tzinfo=timezone.utc), 47),  # March 2029 onward
]

# OID for the TLS Feature extension, used to detect Must-Staple.
TLS_FEATURE_OID = "1.3.6.1.5.5.7.1.24"

OCSP_TIMEOUT_SECONDS = 10


def fetch_certificate_chain(
    hostname: str, port: int = 443
) -> list[x509.Certificate]:
    """
    Fetch the full certificate chain as served by the host. We
    shell out to `openssl s_client -showcerts` rather than using
    Python's ssl module so the chain we parse is exactly what the
    server returned, with no client-side completion. That is the
    point: an incomplete chain (leaf only, no intermediates) is
    one of the failure modes this script is meant to detect.

    Requires the `openssl` CLI on PATH. If the binary is missing
    or its invocation fails, a warning is emitted to stderr and
    an empty list is returned, which the caller surfaces as a
    no_certificate_returned finding.
    """
    try:
        result = subprocess.run(
            [
                "openssl",
                "s_client",
                "-connect",
                f"{hostname}:{port}",
                "-servername",
                hostname,
                "-showcerts",
            ],
            input=b"",
            capture_output=True,
            timeout=OCSP_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        print(
            "WARN: openssl CLI not found on PATH; install it via "
            "`apk add openssl` (Alpine) or `apt-get install openssl` "
            "(Debian/Ubuntu).",
            file=sys.stderr,
        )
        return []
    except subprocess.TimeoutExpired:
        print(
            f"WARN: openssl s_client timed out after "
            f"{OCSP_TIMEOUT_SECONDS}s for {hostname}",
            file=sys.stderr,
        )
        return []

    if result.returncode != 0:
        # openssl ran but reported a non-zero exit. The most common
        # cause is a TLS handshake failure (host unreachable, name
        # mismatch, unsupported protocol). Surface the stderr tail
        # so the caller can see what openssl said instead of
        # silently treating it as "no chain returned".
        err = result.stderr.decode("utf-8", errors="replace").strip()
        if err:
            print(
                f"WARN: openssl s_client returned {result.returncode} "
                f"for {hostname}: {err[:200]}",
                file=sys.stderr,
            )

    output = result.stdout.decode("utf-8", errors="replace")
    certs: list[x509.Certificate] = []
    current_block: list[str] = []
    in_cert = False
    for line in output.splitlines():
        if "-----BEGIN CERTIFICATE-----" in line:
            in_cert = True
            current_block = [line]
        elif "-----END CERTIFICATE-----" in line and in_cert:
            current_block.append(line)
            pem = "\n".join(current_block).encode("ascii")
            try:
                cert = x509.load_pem_x509_certificate(pem, default_backend())
                certs.append(cert)
            except Exception:
                pass
            in_cert = False
        elif in_cert:
            current_block.append(line)
    return certs


def get_san_names(cert: x509.Certificate) -> list[str]:
    try:
        san_ext = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san = san_ext.value
        return [name.value for name in san.get_values_for_type(x509.DNSName)]
    except x509.ExtensionNotFound:
        return []


def hostname_matches_san(hostname: str, san_names: list[str]) -> bool:
    hostname_l = hostname.lower()
    for name in san_names:
        name_l = name.lower()
        if name_l == hostname_l:
            return True
        if name_l.startswith("*."):
            # Wildcard matches exactly one label.
            wildcard_suffix = name_l[2:]
            host_parts = hostname_l.split(".", 1)
            if len(host_parts) == 2 and host_parts[1] == wildcard_suffix:
                return True
    return False


def has_must_staple(cert: x509.Certificate) -> bool:
    """
    Detect the Must-Staple flag by parsing the TLS Feature
    extension (RFC 7633) and looking for the status_request
    feature ID (5). Checking only for the presence of the OID
    would over-report, since the same extension can carry other
    feature IDs such as status_request_v2 (17) without implying
    Must-Staple semantics.
    """
    try:
        ext = cert.extensions.get_extension_for_class(TLSFeature)
    except x509.ExtensionNotFound:
        return False
    return TLSFeatureType.status_request in ext.value


def get_max_allowed_validity_days(issued_at: datetime) -> int:
    """Return the maximum allowed validity for a cert issued on issued_at."""
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    for cutoff, max_days in VALIDITY_SCHEDULE:
        if issued_at < cutoff:
            return max_days
    return VALIDITY_SCHEDULE[-1][1]


def check_ocsp_stapling(hostname: str, port: int = 443) -> dict[str, Any]:
    """
    Probe the host for a stapled OCSP response via
    `openssl s_client -status`. Returns a dict with at least a
    `stapled` boolean. If the openssl invocation fails outright
    (missing binary, timeout, non-zero exit), the dict includes
    an `error` field and stapled is False.
    """
    try:
        result = subprocess.run(
            [
                "openssl",
                "s_client",
                "-connect",
                f"{hostname}:{port}",
                "-servername",
                hostname,
                "-status",
            ],
            input=b"",
            capture_output=True,
            timeout=OCSP_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return {"stapled": False, "error": "openssl CLI not found on PATH"}
    except subprocess.TimeoutExpired:
        return {
            "stapled": False,
            "error": f"openssl s_client timed out after {OCSP_TIMEOUT_SECONDS}s",
        }
    except Exception as exc:
        return {"stapled": False, "error": str(exc)}

    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace").strip()
        print(
            f"WARN: openssl s_client -status returned {result.returncode} "
            f"for {hostname}: {err[:200]}",
            file=sys.stderr,
        )

    output = result.stdout.decode("utf-8", errors="replace")
    stapled = "OCSP Response Status: successful" in output
    return {
        "stapled": stapled,
        "raw_excerpt": "\n".join(
            line for line in output.splitlines()
            if "OCSP" in line or "Cert Status" in line
            or "This Update" in line or "Next Update" in line
        )[:1000],
    }


def audit_hostname(
    hostname: str,
    warn_days: int,
    error_days: int,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    summary: dict[str, Any] = {"hostname": hostname, "findings": findings}

    try:
        chain = fetch_certificate_chain(hostname)
    except Exception as exc:
        findings.append({
            "severity": "error",
            "rule": "tls_handshake_failed",
            "message": f"Could not establish TLS connection, {exc}",
        })
        return summary

    if not chain:
        findings.append({
            "severity": "error",
            "rule": "no_certificate_returned",
            "message": "Server returned no certificate.",
        })
        return summary

    leaf = chain[0]
    summary["chain_length"] = len(chain)
    summary["issuer"] = leaf.issuer.rfc4514_string()
    summary["subject"] = leaf.subject.rfc4514_string()

    not_before = leaf.not_valid_before_utc
    not_after = leaf.not_valid_after_utc
    summary["not_before"] = not_before.isoformat()
    summary["not_after"] = not_after.isoformat()

    # 1. Expiry check
    now = datetime.now(timezone.utc)
    days_remaining = (not_after - now).days
    summary["days_until_expiry"] = days_remaining

    if days_remaining < 0:
        findings.append({
            "severity": "error",
            "rule": "certificate_expired",
            "message": (
                f"Certificate expired {abs(days_remaining)} days ago."
            ),
        })
    elif days_remaining <= error_days:
        findings.append({
            "severity": "error",
            "rule": "certificate_near_expiry",
            "message": (
                f"Certificate expires in {days_remaining} days, "
                f"below error threshold of {error_days}."
            ),
        })
    elif days_remaining <= warn_days:
        findings.append({
            "severity": "warning",
            "rule": "certificate_approaching_expiry",
            "message": (
                f"Certificate expires in {days_remaining} days."
            ),
        })

    # 2. SAN coverage
    san_names = get_san_names(leaf)
    summary["san_names"] = san_names
    if not hostname_matches_san(hostname, san_names):
        findings.append({
            "severity": "error",
            "rule": "hostname_not_in_san",
            "message": (
                f"Hostname {hostname} does not appear in SAN, {san_names}. "
                "Browsers will reject this certificate for this hostname."
            ),
        })

    # 3. Chain completeness
    if len(chain) < 2:
        findings.append({
            "severity": "error",
            "rule": "incomplete_chain",
            "message": (
                "Server returned only the leaf certificate. The full "
                "chain should include at least one intermediate. "
                "This often works in browsers with cached intermediates "
                "and fails everywhere else."
            ),
        })

    # 4. OCSP stapling status
    stapling = check_ocsp_stapling(hostname)
    summary["ocsp_stapling"] = stapling
    must_staple = has_must_staple(leaf)
    summary["must_staple"] = must_staple

    if must_staple and not stapling.get("stapled"):
        findings.append({
            "severity": "error",
            "rule": "must_staple_without_stapling",
            "message": (
                "Certificate has Must-Staple extension but server "
                "does not serve a stapled OCSP response. Compliant "
                "clients will refuse all connections to this host."
            ),
        })
    elif not stapling.get("stapled"):
        findings.append({
            "severity": "warning",
            "rule": "ocsp_stapling_not_active",
            "message": (
                "OCSP stapling is not active. This is not a hard "
                "failure but does reduce TTFB compared to a working "
                "stapling configuration. With Let's Encrypt OCSP "
                "ending in 2025, this may be expected for LE certificates."
            ),
        })

    # 5. Maximum validity check (CA/B Forum SC-081v3)
    max_days_allowed = get_max_allowed_validity_days(not_before)
    actual_days = (not_after - not_before).days
    if actual_days > max_days_allowed:
        findings.append({
            "severity": "warning",
            "rule": "exceeds_max_validity_for_issuance_date",
            "message": (
                f"Certificate validity ({actual_days} days) exceeds "
                f"CA/B Forum maximum of {max_days_allowed} days for "
                f"certificates issued on {not_before.date()}."
            ),
        })

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        help="Single hostname to check.",
    )
    parser.add_argument(
        "--hosts-file",
        help="Path to a file with one hostname per line.",
    )
    parser.add_argument(
        "--warn-days",
        type=int,
        default=30,
        help="Warn if certificate expires within N days. Default 30.",
    )
    parser.add_argument(
        "--error-days",
        type=int,
        default=7,
        help="Error if certificate expires within N days. Default 7.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON report.",
    )
    args = parser.parse_args()

    hostnames: list[str] = []
    if args.host:
        hostnames.append(args.host)
    if args.hosts_file:
        hostnames.extend(
            line.strip()
            for line in Path(args.hosts_file).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    if not hostnames:
        parser.error("Must provide --host or --hosts-file.")

    print(f"Checking {len(hostnames)} hostname(s).", file=sys.stderr)

    results: list[dict[str, Any]] = []
    for hostname in hostnames:
        print(f"  {hostname}", file=sys.stderr)
        try:
            results.append(audit_hostname(
                hostname,
                warn_days=args.warn_days,
                error_days=args.error_days,
            ))
        except Exception as exc:
            results.append({
                "hostname": hostname,
                "findings": [{
                    "severity": "error",
                    "rule": "audit_exception",
                    "message": f"Audit raised, {exc}",
                }],
            })

    error_total = sum(
        1 for r in results for f in r.get("findings", [])
        if f["severity"] == "error"
    )
    warning_total = sum(
        1 for r in results for f in r.get("findings", [])
        if f["severity"] == "warning"
    )

    report = {
        "hostnames_checked": len(hostnames),
        "error_count": error_total,
        "warning_count": warning_total,
        "hosts": results,
    }

    output_text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)

    print(
        f"\nResult, {error_total} errors, {warning_total} warnings "
        f"across {len(hostnames)} hosts.",
        file=sys.stderr,
    )

    if not args.output:
        print(output_text)

    return 1 if error_total > 0 else 0


if __name__ == "__main__":
    sys.exit(main())