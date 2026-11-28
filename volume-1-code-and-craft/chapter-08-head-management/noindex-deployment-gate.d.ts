// Type declarations for noindex-deployment-gate.js, so the TypeScript
// spec (head-audit.spec.ts) can share its robots-directive parser.

export const ROBOTS_META_NAMES: string[];

export class UsageError extends Error {}

export interface Directive {
  agent: string | null;
  directive: string;
}

export interface Blocker {
  type: string;
  message: string;
  detail?: string;
}

export interface Observed {
  http?: { status: number; xRobotsTag: string[] } | { error: string };
  dom?: { status: number | null; meta: { name: string; content: string }[] } | { error: string };
}

export function readUrlsFile(path: string): string[];
export function parseArgs(tokens: string[]): { urls: string[]; urlsFile: string | null; settleMs: number };
export function robotsDirectives(value: string | null | undefined): Directive[];
export function hasNoindex(value: string | null | undefined): boolean;
export function evaluate(observed: Observed): Blocker[];
export function statusLabel(result: { blockers: Blocker[] }): 'PASS' | 'BLOCKED' | 'ERROR';
export function exitCode(results: { blockers: Blocker[] }[]): 0 | 1 | 2;
