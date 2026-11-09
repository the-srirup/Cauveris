import packageJson from "../package.json";

/**
 * Production-grade Application Version Single-Source-of-Truth.
 *
 * Resolves version in standard production priority order:
 * 1. NEXT_PUBLIC_APP_VERSION environment variable (injected during CI/CD, Next.js build, Docker, or Vercel).
 * 2. apps/web/package.json version field.
 * 3. Fallback constant matching the latest GitHub release ("3.0.0").
 */
const rawVersion =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_APP_VERSION) ||
  packageJson.version ||
  "3.1.0";

/**
 * Semantic version string without leading "v" (e.g. "3.0.0").
 */
export const APP_VERSION: string = rawVersion.replace(/^v/, "").trim();

/**
 * Standard GitHub release tag format (e.g. "v3.0.0").
 */
export const APP_VERSION_TAG: string = `v${APP_VERSION}`;

/**
 * Short Git commit SHA hash injected at build time (e.g. "970ed00").
 */
export const GIT_COMMIT_SHA: string =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_GIT_COMMIT_SHA) || "";

/**
 * Full diagnostic provenance string (e.g. "v3.0.0 (970ed00)" or "v3.0.0").
 */
export const APP_FULL_VERSION: string = GIT_COMMIT_SHA
  ? `${APP_VERSION_TAG} (${GIT_COMMIT_SHA})`
  : APP_VERSION_TAG;

/**
 * Canonical release name matching GitHub releases.
 */
export const GITHUB_RELEASE_NAME: string = `Cauveris ${APP_VERSION_TAG}`;

export default APP_VERSION;
