"""Tests for head-audit.py. Pages are served from a local HTTP server."""

from __future__ import annotations

import json
import sys

import pytest
from conftest import load_script

ha = load_script("head-audit.py", "head_audit")


def page(
    url: str,
    *,
    head: str = "",
    body: str = "<h1>Hi</h1>",
    canonical: str | None = None,
    robots: str | None = None,
    title: str = "Merrell Moab 3 GTX, Hiking Boots | OutdoorGear",
) -> str:
    """A page that passes every check unless told otherwise."""
    canonical = url if canonical is None else canonical
    robots_tag = f'<meta name="robots" content="{robots}">' if robots else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{title}</title><meta name="description" content="A description.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{canonical}">{robots_tag}
<meta property="og:title" content="t"><meta property="og:image" content="https://cdn.example/i.png">
<meta property="og:url" content="{url}"><meta name="twitter:card" content="summary">
{head}</head><body>{body}</body></html>"""


def rules_for(html: str, url: str = "https://example.com/p", x_robots_tag=(),
              should_index: bool = True) -> list[str]:
    report = ha.PageReport(url=url)
    head = ha.get_head_data(ha.parse(html))
    ha.check_title(head, report)
    ha.check_canonical(url, head, report, check_status=False)
    ha.check_robots(head, list(x_robots_tag), should_index, report, page_url=url)
    ha.check_description(head, report)
    ha.check_open_graph(head, report)
    ha.check_viewport(head, report)
    ha.check_charset(head, report)
    return [f.rule for f in report.findings]


URL = "https://example.com/p"


def test_clean_page_has_no_findings():
    assert rules_for(page(URL)) == []


# Robots directive parsing -------------------------------------------------

@pytest.mark.parametrize("value", [
    "noindex", "NOINDEX", "none", "index, noindex", "noindex,nofollow",
    "noindex nofollow", "googlebot: noindex", "max-snippet:-1, noindex",
    "otherbot: nofollow, noindex",
])
def test_noindex_values(value):
    assert ha.has_noindex(value)


@pytest.mark.parametrize("value", [
    None, "", "index, follow", "nofollow", "max-image-preview:none",
    "max-image-preview: none", "max-snippet:-1, max-image-preview:large",
    "unavailable_after: 2026-12-31", "googlebot: max-image-preview:none",
    "noimageindex",
])
def test_values_without_noindex(value):
    assert not ha.has_noindex(value)


def test_directives_keep_user_agent_scope():
    assert ha.robots_directives("googlebot: nofollow, max-snippet:20") == [
        ("googlebot", "nofollow"), ("googlebot", "max-snippet"),
    ]


# Head scoping --------------------------------------------------------------

def test_svg_title_in_body_is_not_a_second_title():
    html = page(URL, body='<h1>Hi</h1><svg><title>Cart</title></svg>')
    assert "multiple_titles" not in rules_for(html)


def test_body_canonical_is_ignored():
    html = page(URL, body='<div><link rel="canonical" href="https://example.com/x"></div>')
    assert "multiple_canonicals" not in rules_for(html)


def test_two_head_canonicals_are_flagged():
    html = page(URL, head='<link rel="canonical" href="https://example.com/x">')
    assert "multiple_canonicals" in rules_for(html)


def test_canonical_rel_is_a_token_list_and_case_insensitive():
    html = page(URL).replace('rel="canonical"', 'rel="Canonical"')
    assert "missing_canonical" not in rules_for(html)


def test_canonical_without_href_is_missing():
    html = page(URL).replace(f'<link rel="canonical" href="{URL}">', '<link rel="canonical">')
    assert "missing_canonical" in rules_for(html)


def test_page_without_head_element_still_audits():
    html = '<title>Boots</title><link rel="canonical" href="https://example.com/p">'
    head = ha.get_head_data(ha.parse(html))
    assert head["title"] == "Boots" and head["canonical"] == URL


# Robots meta ---------------------------------------------------------------

def test_uppercase_robots_name_is_detected():
    html = page(URL, head='<meta name="ROBOTS" content="noindex">')
    assert "noindex_on_indexable_page" in rules_for(html)


def test_second_robots_tag_is_detected():
    html = page(URL, head='<meta name="robots" content="max-snippet:-1">'
                          '<meta name="robots" content="noindex">')
    assert "noindex_on_indexable_page" in rules_for(html)


def test_max_image_preview_none_is_not_noindex():
    assert rules_for(page(URL, robots="max-image-preview:none")) == []
    assert rules_for(page(URL), x_robots_tag=["max-image-preview:none"]) == []


def test_x_robots_tag_noindex_is_detected():
    assert "noindex_on_indexable_page" in rules_for(page(URL), x_robots_tag=["googlebot: noindex"])


def test_expected_noindex_is_not_flagged():
    assert rules_for(page(URL, robots="noindex"), should_index=False) == []


# Failure Mode 5 -------------------------------------------------------------

def test_noindex_with_relative_self_canonical_is_not_a_conflict():
    rules = rules_for(page(URL, canonical="/p", robots="noindex"), should_index=False)
    assert "noindex_with_external_canonical" not in rules


def test_noindex_with_canonical_elsewhere_is_a_conflict():
    rules = rules_for(page(URL, canonical="https://example.com/other", robots="noindex"),
                      should_index=False)
    assert "noindex_with_external_canonical" in rules


@pytest.mark.parametrize("a, b", [
    ("https://Example.com/p/", "https://example.com/p"),
    ("https://example.com:443/p#top", "https://example.com/p"),
    ("HTTPS://example.com/", "https://example.com"),
])
def test_normalize_url(a, b):
    assert ha.normalize_url(a) == ha.normalize_url(b)


def test_query_strings_stay_distinct():
    assert ha.normalize_url("https://e.com/p?page=2") != ha.normalize_url("https://e.com/p")


# Canonical host, title, charset ------------------------------------------------

def test_host_comparison_ignores_case_and_default_port():
    html = page(URL, canonical="https://EXAMPLE.com:443/p")
    assert "canonical_host_mismatch" not in rules_for(html)


def test_title_equal_to_site_name_is_generic():
    html = page(URL, title="OutdoorGear",
                head='<meta property="og:site_name" content="OutdoorGear">')
    assert "generic_title" in rules_for(html)


def test_http_equiv_charset_counts_as_a_declaration():
    html = page(URL).replace(
        '<meta charset="utf-8">',
        '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">',
    )
    assert "missing_charset" not in rules_for(html)


def test_utf8_body_without_header_charset_is_not_garbled():
    html = page(URL, title="Café crème").encode("utf-8")
    assert ha.get_head_data(ha.parse(html, None))["title"] == "Café crème"


# Network: fetch, canonical status, sitemaps, main ------------------------------

def test_fetch_keeps_each_x_robots_tag_header(site):
    url = site.add("/p", page("x"), headers=[
        ("X-Robots-Tag", "googlebot: nofollow"),
        ("X-Robots-Tag", "max-image-preview:large"),
    ])
    assert ha.fetch(url).x_robots_tag == ["googlebot: nofollow", "max-image-preview:large"]


def test_audit_uses_the_final_url_after_redirects(site):
    final = site.url("/final")
    site.add("/final", page(final, robots="noindex"))
    start = site.redirect("/start", "/final")
    report = ha.audit(start, should_index=False)
    assert report.final_url == final
    assert [f.rule for f in report.findings if f.severity == "high"] == []


def test_error_status_is_not_audited(site):
    report = ha.audit(site.url("/missing"))
    assert report.fetched is False
    assert report.status_code == 404 and report.error == "HTTP 404"


def test_canonical_that_redirects_is_flagged(site):
    site.add("/good", page(site.url("/good")))
    site.redirect("/moved", "/good")
    url = site.add("/p", page(site.url("/p"), canonical=site.url("/moved")))
    report = ha.audit(url, check_canonical_status=True)
    assert [f.rule for f in report.findings] == ["canonical_not_200"]
    assert "redirects" in report.findings[0].message


def test_canonical_check_falls_back_to_get_when_head_is_rejected(site):
    site.add("/target", page(site.url("/target")), head_status=405)
    url = site.add("/p", page(site.url("/p"), canonical=site.url("/target")))
    assert ha.audit(url, check_canonical_status=True).findings == []


def test_unreachable_canonical(site):
    url = site.add("/p", page(site.url("/p"), canonical="http://127.0.0.1:1/dead"))
    rules = [f.rule for f in ha.audit(url, check_canonical_status=True).findings]
    assert "canonical_unreachable" in rules


def test_sitemap_index_respects_the_limit(site):
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    for name in ("a", "b"):
        locs = "".join(f"<url><loc>{site.url(f'/{name}{i}')}</loc></url>" for i in range(3))
        site.add(f"/{name}.xml", f"<urlset {ns}>{locs}</urlset>",
                 headers=[("Content-Type", "application/xml")])
    index = site.add("/index.xml", f"<sitemapindex {ns}>"
                     f"<sitemap><loc>{site.url('/a.xml')}</loc></sitemap>"
                     f"<sitemap><loc>{site.url('/b.xml')}</loc></sitemap></sitemapindex>",
                     headers=[("Content-Type", "application/xml")])
    assert ha.parse_sitemap(index, limit=4) == [
        site.url("/a0"), site.url("/a1"), site.url("/a2"), site.url("/b0"),
    ]


def run_main(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["head-audit.py", *argv])
    code = ha.main()
    return code, capsys.readouterr()


def test_main_exit_codes(site, monkeypatch, capsys):
    good = site.add("/good", page(site.url("/good")))
    bad = site.add("/bad", page(site.url("/bad")).replace("<title>", "<x>").replace("</title>", "</x>"))

    code, out = run_main(monkeypatch, capsys, "--url", good)
    assert code == 0 and json.loads(out.out)["summary"]["urls_fetched"] == 1

    code, _ = run_main(monkeypatch, capsys, "--url", bad)
    assert code == 1


def test_unfetchable_url_is_not_a_pass(site, monkeypatch, capsys):
    code, out = run_main(monkeypatch, capsys, "--url", site.url("/missing"))
    assert code == 2
    assert json.loads(out.out)["reports"][0]["status_code"] == 404
    assert out.err.startswith("ERROR")


def test_high_finding_wins_over_fetch_error(site, monkeypatch, capsys, tmp_path):
    bad = site.add("/bad", page(site.url("/bad"), robots="noindex"))
    urls = tmp_path / "urls.txt"
    urls.write_text(f"# list\n{bad}\n{site.url('/missing')}\n{site.url('/x')}  noindex\n")
    code, _ = run_main(monkeypatch, capsys, "--urls-file", str(urls))
    assert code == 1


def test_urls_file_noindex_token(tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text("https://e.com/a\nhttps://e.com/b   NOINDEX\n\n# c\n")
    assert ha.read_targets(str(urls)) == [("https://e.com/a", True), ("https://e.com/b", False)]


@pytest.mark.parametrize("argv", [
    ["--urls-file", "/no/such/file.txt"],
    ["--urls-file", "EMPTY"],
    ["--url", "https://e.com/", "--limit", "0"],
])
def test_usage_errors_exit_two(tmp_path, monkeypatch, capsys, argv):
    empty = tmp_path / "empty.txt"
    empty.write_text("# only a comment\n")
    argv = [str(empty) if a == "EMPTY" else a for a in argv]
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, capsys, *argv)
    assert exc.value.code == 2


def test_unreadable_sitemap_exits_two(site, monkeypatch, capsys):
    code, out = run_main(monkeypatch, capsys, "--sitemap", site.url("/nope.xml"))
    assert code == 2 and "cannot read sitemap" in out.err
