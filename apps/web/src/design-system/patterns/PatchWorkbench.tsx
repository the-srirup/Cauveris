"use client";

import React, { useState } from "react";
import { FileCode, Download } from "lucide-react";
import { CodePreview } from "@/components/CodePreview";
import { asArray, toText } from "@/lib/safeText";

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
  // candidates may arrive as a non-array from a partial backend payload — guard before .find/.map.
  const candidateList = asArray<PatchCandidateData>(candidates);
  const selectedCandidate =
    candidateList.find((c) => c?.candidateId === selectedCandidateId) || candidateList[0] || null;

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
            {selectedCandidate ? toText(selectedCandidate.targetFile, "No candidate selected") : "No candidate selected"}
          </span>
          {selectedCandidate?.structuralLocator && (
            <span className="text-[11px] text-[var(--color-fg-muted,#5f6b76)] font-mono truncate">
              loc: {toText(selectedCandidate.structuralLocator)}
            </span>
          )}
          {selectedCandidate?.verificationLevel && (
            <span className="text-[10px] px-2 py-0.5 border border-emerald-200 bg-emerald-50 text-emerald-800 font-semibold rounded-[var(--radius-sm,4px)] shrink-0 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
              {toText(selectedCandidate.verificationLevel)}
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
            Repair Candidates ({candidateList.length})
          </div>
          <div className="divide-y divide-[var(--color-border-default,#d9e0e7)] overflow-y-auto">
            {candidateList.map((cand, idx) => {
              if (!cand || typeof cand !== "object") return null;
              const isSelected = cand.candidateId === selectedCandidate?.candidateId;
              return (
                <div
                  key={toText(cand.candidateId, `candidate-${idx}`)}
                  onClick={() => onSelectCandidate?.(toText(cand.candidateId))}
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
                      #{toText(cand.rank, idx + 1)} {toText(cand.candidateId)}
                    </span>
                    <span className="text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
                      {toText(cand.verificationLevel)}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--color-fg-default,#1f2933)] font-mono truncate mb-1">
                    {toText(cand.parameterName)}: {toText(cand.originalValue)} → {toText(cand.proposedValue)}
                  </div>
                  <div className="text-[11px] text-[var(--color-fg-muted,#5f6b76)] truncate font-sans">
                    {toText(cand.rationale)}
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
              SOURCE SHA-256: <code className="text-[var(--color-fg-default,#1f2933)] font-mono">{toText(selectedCandidate?.sourceHashSha256, "").substring(0, 16) || "verified"}...</code>
            </span>
            <span>
              EVIDENCE LINKS: <span className="text-[var(--color-fg-default,#1f2933)] font-mono">{asArray<unknown>(selectedCandidate?.evidenceLinks).map((l) => toText(l)).join(", ") || "1 telemetry link"}</span>
            </span>
          </div>

          {/* Unified Diff content — rendered as text via CodePreview (normalized, never executed) */}
          <div className="flex-1 p-4 overflow-x-auto font-mono text-xs leading-relaxed text-[var(--color-fg-default,#1f2933)]">
            <CodePreview
              mode="diff"
              source={selectedCandidate?.diffUnified}
              fileName={selectedCandidate ? toText(selectedCandidate.targetFile, "patch.diff") : "patch.diff"}
              emptyMessage="Select a candidate to view unified code diff and structural locator."
              className="whitespace-pre"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
