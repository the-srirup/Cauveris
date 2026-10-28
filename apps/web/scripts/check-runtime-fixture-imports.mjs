/**
 * CI Guard: Production frontend code must not import test fixtures, mocks, or sample data.
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const WEB_ROOT = path.resolve(__dirname, "..");

const PRODUCTION_DIRS = [
  path.join(WEB_ROOT, "app"),
  path.join(WEB_ROOT, "components"),
  path.join(WEB_ROOT, "lib"),
  path.join(WEB_ROOT, "hooks"),
  path.join(WEB_ROOT, "src"),
];

const FORBIDDEN_IMPORT_PATTERNS = [
  /from\s+['"].*\/__tests__\/.*['"]/,
  /from\s+['"].*\/fixtures\/.*['"]/,
  /from\s+['"].*mock.*['"]/i,
  /import\s+['"].*\/__tests__\/.*['"]/,
  /import\s+['"].*\/fixtures\/.*['"]/,
];

function scanDir(dir, violations) {
  if (!fs.existsSync(dir)) return;
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      if (entry.name === "__tests__" || entry.name === "node_modules" || entry.name === ".next" || entry.name === "e2e") {
        continue; // skip test and build directories
      }
      scanDir(fullPath, violations);
    } else if (entry.isFile() && (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx"))) {
      if (entry.name.includes(".test.") || entry.name.includes(".spec.")) {
        continue; // skip test files
      }

      const content = fs.readFileSync(fullPath, "utf-8");
      const lines = content.split("\n");

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        for (const pattern of FORBIDDEN_IMPORT_PATTERNS) {
          if (pattern.test(line)) {
            const relPath = path.relative(WEB_ROOT, fullPath);
            violations.push(`${relPath}:${i + 1}: ${line.trim()}`);
          }
        }
      }
    }
  }
}

const violations = [];
for (const pDir of PRODUCTION_DIRS) {
  scanDir(pDir, violations);
}

if (violations.length > 0) {
  console.error("Runtime fixture/mock imports detected in production frontend code:");
  console.error(violations.join("\n"));
  process.exit(1);
} else {
  console.log("Frontend runtime fixture guard passed: Zero test fixtures imported in production code.");
  process.exit(0);
}
