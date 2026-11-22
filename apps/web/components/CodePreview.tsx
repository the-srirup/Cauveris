"use client";

/**
 * Text-only source / diff preview.
 *
 * Guarantees:
 * - code is rendered as text (per-line <span> children), never as HTML and
 *   never executed — no dangerouslySetInnerHTML anywhere in this path
 * - source is normalized through toText() before rendering, so objects,
 *   null, or wrong-typed data can never crash the render
 * - empty input renders an explicit empty state, binary input renders a
 *   clear "unavailable" state — neither throws
 */

import React, { forwardRef, useMemo } from "react";
import { FileCode2, FileQuestion, FileWarning } from "lucide-react";
import { asArray, isProbablyBinary, splitLines, toText } from "@/lib/safeText";

export interface CodePreviewProps
  extends Omit<React.HTMLAttributes<HTMLPreElement>, "children"> {
  /** Raw source/diff content — any type; normalized internally. */
  source: unknown;
  mode?: "source" | "diff";
  fileName?: string;
  maxLines?: number;
  showLineNumbers?: boolean;
  emptyMessage?: string;
}

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-zinc-500";
  if (line.startsWith("+")) return "text-emerald-400/90 bg-emerald-500/5";
  if (line.startsWith("-")) return "text-red-400/90 bg-red-500/5";
  if (line.startsWith("@@")) return "text-sky-400/90";
  if (line.startsWith("diff ") || line.startsWith("index ")) return "text-zinc-500 font-semibold";
  return "text-zinc-300";
}

export const CodePreview = forwardRef<HTMLPreElement, CodePreviewProps>(function CodePreview(
  {
    source,
    mode = "source",
    fileName,
    maxLines,
    showLineNumbers = false,
    emptyMessage,
    className = "",
    ...rest
  },
  ref
) {
  const text = useMemo(() => toText(source, ""), [source]);
  const binary = useMemo(() => isProbablyBinary(text), [text]);
  const lines = useMemo(() => {
    if (binary) return [] as string[];
    const all = splitLines(text);
    const limited = maxLines && maxLines > 0 ? all.slice(0, maxLines) : all;
    return limited;
  }, [text, binary, maxLines]);
  const truncated = !binary && maxLines != null && maxLines > 0 && splitLines(text).length > maxLines;

  if (binary) {
    return (
      <div
        role="status"
        data-preview-state="binary"
        className={`flex h-full min-h-24 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-[var(--divider,#27272a)] bg-[var(--panel-recessed,#0e0e11)] p-6 text-center ${className}`}
      >
        <FileWarning className="h-5 w-5 text-amber-400" aria-hidden="true" />
        <p className="text-xs font-medium text-[var(--text-secondary,#a1a1aa)]">
          Binary content — text preview unavailable
        </p>
        <p className="text-[11px] text-[var(--text-tertiary,#71717a)]">
          {fileName ? `${toText(fileName)} is not displayable as text.` : "This file is not displayable as text."}
        </p>
      </div>
    );
  }

  if (text.length === 0) {
    return (
      <div
        role="status"
        data-preview-state="empty"
        className={`flex h-full min-h-24 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-[var(--divider,#27272a)] bg-[var(--panel-recessed,#0e0e11)] p-6 text-center ${className}`}
      >
        <FileQuestion className="h-5 w-5 text-[var(--text-tertiary,#71717a)]" aria-hidden="true" />
        <p className="text-xs text-[var(--text-tertiary,#71717a)]">
          {emptyMessage ?? (mode === "diff" ? "No diff available for this patch." : "No source to preview.")}
        </p>
      </div>
    );
  }

  return (
    <pre
      ref={ref}
      data-preview-state="ok"
      data-preview-mode={mode}
      aria-label={fileName ? `Source preview for ${toText(fileName)}` : "Source preview"}
      className={`overflow-auto whitespace-pre font-mono text-[11px] leading-relaxed ${className}`}
      {...rest}
    >
      {lines.map((line, i) => (
        <div key={i} className={`flex min-w-max ${mode === "diff" ? diffLineClass(line) : ""}`}>
          {showLineNumbers && (
            <span
              aria-hidden="true"
              className="w-10 shrink-0 select-none pr-3 text-right text-zinc-600"
            >
              {i + 1}
            </span>
          )}
          {/* Plain string child — React escapes it; code is displayed, never executed. */}
          <span className="whitespace-pre">{line || " "}</span>
        </div>
      ))}
      {truncated && (
        <div className="min-w-max pt-1 text-zinc-600">
          … {splitLines(text).length - (maxLines ?? 0)} more lines (truncated)
        </div>
      )}
    </pre>
  );
});

/** Convenience wrapper for unified diffs. */
export function DiffPreview(
  props: Omit<CodePreviewProps, "mode"> & { mode?: "diff" }
) {
  return <CodePreview mode="diff" showLineNumbers {...props} />;
}

/** Convenience wrapper for plain source files. */
export function SourcePreview(props: Omit<CodePreviewProps, "mode">) {
  return <CodePreview mode="source" showLineNumbers fileName={props.fileName ?? "source"} {...props} />;
}

export default CodePreview;

// Re-export for call sites that branch on array-shaped data inline.
export { asArray, toText };
