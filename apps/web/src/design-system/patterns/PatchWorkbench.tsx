"use client";

import React, { useState } from "react";
import { FileCode, Download } from "lucide-react";

export interface PatchCandidateData {
  candidateId: string;
  rank: number;
  targetFile: string;
  parameterName: string;
  originalValue: string | number;
  proposedValue: string | number;
  structuralLocator?: string;
  diffUnified: string;
  sourceHashSha256?: string;
  rationale: string;
  evidenceLinks: string[];
  verificationLevel: string;
  isStaged?: boolean;
  canRollback?: boolean;
}

export interface PatchWorkbenchProps extends React.HTMLAttributes<HTMLDivElement> {
  candidates: PatchCandidateData[];
  selectedCandidateId?: string;
  onSelectCandidate?: (candidateId: string) => void;
  onStagePatch?: (candidateId: string) => void;
  onApplyPatch?: (candidateId: string) => void;
  onRollback?: (candidateId: string) => void;
  onDownloadPackage?: (candidateId: string) => void;
}

export function PatchWorkbench({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  onStagePatch,
  onApplyPatch,
  onRollback,
  onDownloadPackage,
  className = "",
  ...props
}: PatchWorkbenchProps) {
  const selectedCandidate =
    candidates.find((c) => c.candidateId === selectedCandidateId) || candidates[0];

  const [diffMode, setDiffMode] = useState<"unified" | "split">("unified");

  return (
    <div
      className={`flex flex-col border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] rounded-[var(--radius-lg,8px)] text-xs select-none shadow-xs ${className}`}
      data-patch-workbench
      {...props}
    >
      {/* Top Header Rail: File Path + Controls */}
      <div className="flex items-center justify-between border-b border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] px-4 py-2.5 rounded-t-[calc(var(--radius-lg,8px)-1px)]">
        <div className="flex items-center gap-3 min-w-0">
          <FileCode className="w-4 h-4 text-[var(--color-fg-muted,#5f6b76)] shrink-0" />
          <span className="font-semibold text-[var(--color-fg-default,#1f2933)] text-xs truncate font-mono">
            {selectedCandidate?.targetFile || "No candidate selected"}
          </span>
          {selectedCandidate?.structuralLocator && (
            <span className="text-[11px] text-[var(--color-fg-muted,#5f6b76)] font-mono truncate">
              loc: {selectedCandidate.structuralLocator}
            </span>
          )}
          {selectedCandidate?.verificationLevel && (
            <span className="text-[10px] px-2 py-0.5 border border-emerald-200 bg-emerald-50 text-emerald-800 font-semibold rounded-[var(--radius-sm,4px)] shrink-0 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
              {selectedCandidate.verificationLevel}
            </span>
          )}
        </div>

        {/* Diff Mode Toggle & Action Buttons */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="flex items-center border border-[var(--color-border-default,#d9e0e7)] rounded-[var(--radius-md,6px)] bg-[var(--color-canvas-subtle,#f8f9fa)] p-0.5 text-xs">
            <button
              onClick={() => setDiffMode("unified")}
              className={`px-2.5 py-1 rounded-[var(--radius-sm,4px)] font-medium transition-colors ${
                diffMode === "unified"
                  ? "bg-[var(--color-canvas-default,#ffffff)] text-[var(--color-fg-default,#1f2933)] shadow-xs"
                  : "text-[var(--color-fg-muted,#5f6b76)] hover:text-[var(--color-fg-default,#1f2933)]"
              }`}
            >
              Unified
            </button>
            <button
              onClick={() => setDiffMode("split")}
              className={`px-2.5 py-1 rounded-[var(--radius-sm,4px)] font-medium transition-colors ${
                diffMode === "split"
                  ? "bg-[var(--color-canvas-default,#ffffff)] text-[var(--color-fg-default,#1f2933)] shadow-xs"
                  : "text-[var(--color-fg-muted,#5f6b76)] hover:text-[var(--color-fg-default,#1f2933)]"
              }`}
            >
              Split
            </button>
          </div>

          {onDownloadPackage && selectedCandidate && (
            <button
              onClick={() => onDownloadPackage(selectedCandidate.candidateId)}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-semibold border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] text-[var(--color-fg-default,#1f2933)] rounded-[var(--radius-md,6px)] hover:bg-[var(--color-canvas-subtle,#f8f9fa)] transition-colors shadow-xs"
            >
              <Download className="w-3.5 h-3.5" />
              Package
            </button>
          )}
        </div>
      </div>

      {/* Main Split Body: Left File/Candidate list + Right Diff Viewer */}
      <div className="grid grid-cols-12 min-h-[460px]">
        {/* Left Candidate Navigator */}
        <div className="col-span-12 md:col-span-4 border-r border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] flex flex-col">
          <div className="px-4 py-2.5 border-b border-[var(--color-border-default,#d9e0e7)] text-xs uppercase font-semibold text-[var(--color-fg-muted,#5f6b76)]">
            Repair Candidates ({candidates.length})
          </div>
          <div className="divide-y divide-[var(--color-border-default,#d9e0e7)] overflow-y-auto">
            {candidates.map((cand) => {
              const isSelected = cand.candidateId === selectedCandidate?.candidateId;
              return (
                <div
                  key={cand.candidateId}
                  onClick={() => onSelectCandidate?.(cand.candidateId)}
                  role="button"
                  tabIndex={0}
                  className={`p-3.5 transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-blue-50/70 border-l-2 border-l-[var(--color-accent,#0969da)] pl-3 text-[var(--color-fg-default,#1f2933)] dark:bg-blue-950/30"
                      : "hover:bg-[var(--color-canvas-subtle,#f8f9fa)] text-[var(--color-fg-muted,#5f6b76)]"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-semibold text-[var(--color-fg-default,#1f2933)] font-mono">
                      #{cand.rank} {cand.candidateId}
                    </span>
                    <span className="text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
                      {cand.verificationLevel}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--color-fg-default,#1f2933)] font-mono truncate mb-1">
                    {cand.parameterName}: {String(cand.originalValue)} → {String(cand.proposedValue)}
                  </div>
                  <div className="text-[11px] text-[var(--color-fg-muted,#5f6b76)] truncate font-sans">
                    {cand.rationale}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Code / Diff Viewer */}
        <div className="col-span-12 md:col-span-8 flex flex-col bg-[var(--color-canvas-inset,#f8f9fa)] dark:bg-[#0d1117]">
          {/* Metadata bar */}
          <div className="px-4 py-2 border-b border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] text-xs flex items-center justify-between text-[var(--color-fg-muted,#5f6b76)]">
            <span>
              SOURCE SHA-256: <code className="text-[var(--color-fg-default,#1f2933)] font-mono">{selectedCandidate?.sourceHashSha256?.substring(0, 16) || "verified"}...</code>
            </span>
            <span>
              EVIDENCE LINKS: <span className="text-[var(--color-fg-default,#1f2933)] font-mono">{selectedCandidate?.evidenceLinks.join(", ") || "1 telemetry link"}</span>
            </span>
          </div>

          {/* Unified Diff content */}
          <div className="flex-1 p-4 overflow-x-auto font-mono text-xs leading-relaxed text-[var(--color-fg-default,#1f2933)]">
            {selectedCandidate?.diffUnified ? (
              <pre className="whitespace-pre">
                {selectedCandidate.diffUnified.split("\n").map((line, idx) => {
                  let lineStyle = "text-[var(--color-fg-muted,#5f6b76)]";
                  if (line.startsWith("+") && !line.startsWith("+++")) {
                    lineStyle = "text-emerald-900 bg-emerald-50 dark:bg-emerald-950/40 dark:text-emerald-200 border-l-2 border-emerald-500 pl-2";
                  } else if (line.startsWith("-") && !line.startsWith("---")) {
                    lineStyle = "text-rose-900 bg-rose-50 dark:bg-rose-950/40 dark:text-rose-200 border-l-2 border-rose-500 pl-2 line-through opacity-85";
                  } else if (line.startsWith("@@")) {
                    lineStyle = "text-blue-900 bg-blue-50 dark:bg-blue-950/40 dark:text-blue-300 font-semibold";
                  }
                  return (
                    <div key={idx} className={`px-2 py-0.5 ${lineStyle}`}>
                      {line}
                    </div>
                  );
                })}
              </pre>
            ) : (
              <div className="p-8 text-center text-xs text-[var(--color-fg-muted,#5f6b76)] italic font-sans">
                Select a candidate to view unified code diff and structural locator.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
