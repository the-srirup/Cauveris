import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Read package.json version
let pkgVersion = "3.1.0";
try {
  const pkgPath = path.join(__dirname, "package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
  if (pkg.version) {
    pkgVersion = pkg.version;
  }
} catch {
  // Use fallback
}

// Dynamically resolve active Git release tag and commit hash at build time
let gitTag = "";
let gitSha = "";

try {
  gitTag = execSync("git describe --tags --abbrev=0", {
    cwd: __dirname,
    stdio: ["ignore", "pipe", "ignore"],
  })
    .toString()
    .trim();
} catch {
  // Fall back to package version
  gitTag = `v${pkgVersion}`;
}

try {
  gitSha = execSync("git rev-parse --short HEAD", {
    cwd: __dirname,
    stdio: ["ignore", "pipe", "ignore"],
  })
    .toString()
    .trim();
} catch {
  // Omit SHA if not in git worktree
  gitSha = "";
}

const resolvedVersion =
  process.env.NEXT_PUBLIC_APP_VERSION || `v${pkgVersion}`;
const resolvedSha = process.env.NEXT_PUBLIC_GIT_COMMIT_SHA || gitSha;

/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_APP_VERSION: resolvedVersion,
    NEXT_PUBLIC_GIT_COMMIT_SHA: resolvedSha,
  },
  turbopack: {
    root: path.resolve(__dirname, "../.."),
  },
};

export default nextConfig;
