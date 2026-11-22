/**
 * Normalization helpers for rendering untrusted or partial backend data.
 *
 * Rule enforced across every preview path: anything the API hands back may be
 * missing, null, the wrong primitive, an object, or binary. All of it funnels
 * through these helpers before React ever sees it, so a render can never throw
 * "Objects are not valid as a React child" or a TypeError from calling
 * .split/.map/.toFixed on the wrong type.
 */

/**
 * Fallback values may be any primitive. Callers routinely pass a numeric
 * placeholder (rank 1, count 0) or null when the value is genuinely absent,
 * so the fallback is coerced to a string here rather than forcing every
 * call site to stringify it by hand.
 */
export type TextFallback = string | number | null | undefined;

function coerceFallback(fallback: TextFallback): string {
  if (fallback === null || fallback === undefined) return "";
  return typeof fallback === "string" ? fallback : String(fallback);
}

/** Coerce any value to a display string. Objects become pretty JSON; circular/unstringifiable values degrade to a placeholder instead of throwing. */
export function toText(value: unknown, fallback: TextFallback = ""): string {
  const fb = coerceFallback(fallback);
  if (value === null || value === undefined) return fb;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "bigint") {
    return Number.isFinite(Number(value)) ? String(value) : fb;
  }
  if (typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value
      .map((item) => toText(item, fb))
      .filter((part) => part.length > 0 || fb.length > 0)
      .join("\n");
  }
  if (typeof value === "object") {
    const json = safeJsonStringify(value, 2);
    return json || fb || "[unprintable value]";
  }
  try {
    return String(value);
  } catch {
    return fb || "[unprintable value]";
  }
}

/** JSON.stringify that can never throw (circular refs, BigInt, etc.). */
export function safeJsonStringify(value: unknown, space?: number, fallback: TextFallback = ""): string {
  const fb = coerceFallback(fallback);
  try {
    const seen = new WeakSet<object>();
    const out = JSON.stringify(
      value,
      (_key, val: unknown) => {
        if (typeof val === "bigint") return val.toString();
        if (typeof val === "object" && val !== null) {
          if (seen.has(val)) return "[circular]";
          seen.add(val);
        }
        return val;
      },
      space
    );
    return typeof out === "string" ? out : fb;
  } catch {
    return fb;
  }
}

/** Array.isArray guard — returns the value only when it is a real array. */
export function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

/** Normalize line endings and split into lines. Input must already be a string. */
export function splitLines(text: string): string[] {
  return text.replace(/\r\n?/g, "\n").split("\n");
}

const CONTROL_CHARS = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/;

/** Heuristic binary detection: NUL bytes or a high ratio of control characters. */
export function isProbablyBinary(text: string): boolean {
  if (!text) return false;
  if (text.includes("\0")) return true;
  const sample = text.slice(0, 8000);
  if (sample.length === 0) return false;
  let control = 0;
  for (let i = 0; i < sample.length; i++) {
    if (CONTROL_CHARS.test(sample[i])) control++;
  }
  return control / sample.length > 0.05;
}

/** Escape a value for interpolation into generated HTML (downloads, exports). Never for rendering into the live DOM. */
export function escapeHtml(value: unknown): string {
  return toText(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Coerce to a finite number, with fallback. Guards every .toFixed/.toExponential/arithmetic render path. */
export function toFiniteNumber(value: unknown, fallback = 0): number {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) ? n : fallback;
}
