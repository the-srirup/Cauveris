"use client";

import { useState, useEffect, type ReactNode } from "react";
import { X, FileText, Shield, Link as LinkIcon, AlertTriangle, Database, Zap, Search, Eye, ExternalLink, Clock, GitBranch, FlaskConical, Wrench, Check } from "lucide-react";
import { Tabs } from "./Tabs";
import { Divider } from "./Divider";
import { Badge, Button } from "./ui";
import { Tooltip } from "./Tooltip";
import { useShell } from "@/lib/useShell";
import { useShellLayout } from "@/hooks/useMediaQuery";
import type { InspectorData, InspectorMode } from "@/lib/useShell";

export function RightInspector() {
  const {
    state: { inspectorOpen, inspectorMode, inspectorData },
    closeInspector,
  } = useShell();
  const { isInspectorDrawer } = useShellLayout();
  const [activeTab, setActiveTab] = useState("provenance");

  if (!inspectorOpen || !inspectorMode) return null;

  const isDrawer = isInspectorDrawer;

  return (
    <>
      {/* Backdrop for drawer mode on mobile/tablet */}
      {isDrawer && inspectorOpen && (
        <div
          className="fixed inset-0 z-[var(--z-modal)] bg-[var(--color-canvas)]/80 lg:hidden"
          onClick={closeInspector}
          aria-hidden="true"
        />
      )}
      <aside
        className={`
          fixed inset-y-0 right-0 z-[var(--z-modal)]
          bg-[var(--workspace,#121215)]
          border-l border-[var(--divider,#27272a)]
          flex flex-col transition-transform duration-200 ease-out font-mono
          ${inspectorOpen ? "translate-x-0" : "translate-x-full"}
          ${isDrawer ? "w-full max-w-[90vw]" : "w-[var(--shell-inspector-width)]"}
        `}
        role="complementary"
        aria-label={`Inspector: ${inspectorMode}`}
        data-mode={inspectorMode}
        data-context-dock
      >
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--divider,#27272a)] bg-[var(--panel-recessed,#0e0e11)]">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-7 w-7 items-center justify-center rounded-[2px] bg-zinc-800 border border-zinc-700 text-zinc-200 shrink-0">
              {getModeIcon(inspectorMode)}
            </div>
            <div className="min-w-0">
              <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary,#f4f4f5)] truncate m-0">
                {getModeLabel(inspectorMode)}
              </h3>
              <p className="text-[10px] text-[var(--text-tertiary,#71717a)] truncate mt-0.5">
                {getModeDescription(inspectorMode, inspectorData)}
              </p>
            </div>
          </div>
          <Tooltip content="Close inspector" position="left">
            <button
              onClick={closeInspector}
              className="flex h-7 w-7 items-center justify-center rounded-[2px] text-[var(--text-tertiary,#71717a)] hover:text-[var(--text-primary,#f4f4f5)] hover:bg-[var(--panel,#18181b)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              aria-label="Close inspector"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </Tooltip>
        </header>

        {/* Tabbed Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <Tabs value={activeTab} onValueChange={setActiveTab} variant="line" size="sm">
            <Tabs.List aria-label="Inspector tabs" className="mb-2">
              <Tabs.Trigger value="provenance" icon={<FileText className="h-3.5 w-3.5" />}>
                Provenance
              </Tabs.Trigger>
              <Tabs.Trigger value="confidence" icon={<Shield className="h-3.5 w-3.5" />}>
                Confidence
              </Tabs.Trigger>
              <Tabs.Trigger value="related" icon={<LinkIcon className="h-3.5 w-3.5" />}>
                Related
              </Tabs.Trigger>
              <Tabs.Trigger value="evidence" icon={<Database className="h-3.5 w-3.5" />}>
                Evidence
              </Tabs.Trigger>
            </Tabs.List>
            <Tabs.Content value="provenance" forceMount>
              <ProvenancePanel data={inspectorData} />
            </Tabs.Content>
            <Tabs.Content value="confidence" forceMount>
              <ConfidencePanel data={inspectorData} />
            </Tabs.Content>
            <Tabs.Content value="related" forceMount>
              <RelatedPanel data={inspectorData} />
            </Tabs.Content>
            <Tabs.Content value="evidence" forceMount>
              <EvidencePanel data={inspectorData} />
            </Tabs.Content>
          </Tabs>
        </div>
      </aside>
    </>
  );
}

function ProvenancePanel({ data }: { data: InspectorData }) {
  if (!data.mode) return <EmptyState message="No element selected" />;

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">Source Artifacts</h4>
        <div className="space-y-2">
          {data.elementData?.source_artifacts?.map((artifact: any, i: number) => (
            <ArtifactRow key={i} artifact={artifact} />
          )).length || (
            <div className="text-sm text-[var(--color-fg-muted)] text-center py-4">No source artifacts recorded</div>
          )}
        </div>
      </div>

      <Divider />

      <div>
        <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">Lineage</h4>
        <div className="space-y-2">
          {data.elementData?.lineage?.map((step: any, i: number) => (
            <LineageStep key={i} step={step} />
          )).length || (
            <div className="text-sm text-[var(--color-fg-muted)] text-center py-4">No lineage data available</div>
          )}
        </div>
      </div>

      <Divider />

      <div>
        <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">Timestamps</h4>
        <div className="space-y-1">
          {data.elementData?.created_at && (
            <KVRow label="Created" value={formatTimestamp(data.elementData.created_at)} />
          )}
          {data.elementData?.updated_at && (
            <KVRow label="Updated" value={formatTimestamp(data.elementData.updated_at)} />
          )}
          {data.elementData?.ingested_at && (
            <KVRow label="Ingested" value={formatTimestamp(data.elementData.ingested_at)} />
          )}
          {data.evidenceData?.ingested_at && (
            <KVRow label="Ingested" value={formatTimestamp(data.evidenceData.ingested_at)} />
          )}
          {!data.elementData?.created_at && !data.elementData?.updated_at && !data.elementData?.ingested_at && !data.evidenceData?.ingested_at && (
            <div className="text-sm text-[var(--color-fg-muted)] text-center py-4">No timestamps available</div>
          )}
        </div>
      </div>

      <Divider />

      <div>
        <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">Checksums</h4>
        <div className="space-y-1">
          {data.elementData?.checksum && (
            <KVRow label="SHA-256" value={<code className="font-mono text-xs text-[var(--color-fg-muted)] bg-[var(--color-canvas-subtle)] px-1.5 py-0.5 rounded-[var(--radius-sm)]">{data.elementData.checksum}</code>} />
          )}
          {data.evidenceData?.checksum && (
            <KVRow label="SHA-256" value={<code className="font-mono text-xs text-[var(--color-fg-muted)] bg-[var(--color-canvas-subtle)] px-1.5 py-0.5 rounded-[var(--radius-sm)]">{data.evidenceData.checksum}</code>} />
          )}
          {data.hypothesisData?.checksum && (
            <KVRow label="SHA-256" value={<code className="font-mono text-xs text-[var(--color-fg-muted)] bg-[var(--color-canvas-subtle)] px-1.5 py-0.5 rounded-[var(--radius-sm)]">{data.hypothesisData.checksum}</code>} />
          )}
          {!data.elementData?.checksum && !data.evidenceData?.checksum && !data.hypothesisData?.checksum && (
            <div className="text-sm text-[var(--color-fg-muted)] text-center py-4">No checksums available</div>
          )}
        </div>
      </div>
    </div>
  );
}

function ConfidencePanel({ data }: { data: InspectorData }) {
  if (!data.mode) return <EmptyState message="No element selected" />;

  const confidence = data.elementData?.confidence ?? data.hypothesisData?.confidence ?? data.evidenceData?.confidence;
  const uncertainty = data.elementData?.uncertainty ?? data.hypothesisData?.uncertainty;

  return (
    <div className="space-y-4">
      {confidence !== undefined && (
        <div>
          <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">Confidence Score</h4>
          <div className="flex items-center gap-4">
            <div className="relative flex-shrink-0" style={{ width: 72, height: 72 }}>
              <svg viewBox="0 0 72 72" className="w-full h-full transform -rotate-90">
                <circle
                  cx="36"
                  cy="36"
                  r="32"
                  fill="none"
                  stroke="var(--color-border-default)"
                  strokeWidth="4"
                />
                <circle
                  cx="36"
                  cy="36"
                  r="32"
                  fill="none"
                  stroke={getConfidenceColor(confidence)}
                  strokeWidth="4"
                  strokeDasharray={201}
                  strokeDashoffset={201 * (1 - confidence / 100)}
                  strokeLinecap="round"
                  className="transition-all duration-500"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-xl font-mono font-bold text-[var(--color-fg-default)]">{Math.round(confidence)}%</span>
              </div>
            </div>
            <div className="flex-1 space-y-2">
              <div>
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-fg-muted)]">Lower Bound</span>
                  <span className="font-medium">{Math.round((confidence - (uncertainty || 0)) * 100) / 100}%</span>
                </div>
                <div className="h-1.5 bg-[var(--color-canvas-subtle)] rounded-full overflow-hidden mt-1">
                  <div
                    className="h-full bg-[var(--color-success-emphasis)]"
                    style={{ width: `${Math.max(0, confidence - (uncertainty || 0))}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-fg-muted)]">Upper Bound</span>
                  <span className="font-medium">{Math.round((confidence + (uncertainty || 0)) * 100) / 100}%</span>
                </div>
                <div className="h-1.5 bg-[var(--color-canvas-subtle)] rounded-full overflow-hidden mt-1">
                  <div
                    className="h-full bg-[var(--color-accent-emphasis)]"
                    style={{ width: `${Math.min(100, confidence + (uncertainty || 0))}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {confidence !== undefined && uncertainty !== undefined && (
        <Divider />
      )}

      {uncertainty !== undefined && (
        <div>
          <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">Uncertainty</h4>
          <div className="space-y-2">
            <KVRow label="Uncertainty Range" value={`±${uncertainty.toFixed(2)}%`} />
            <KVRow label="Calibration" value={uncertainty < 5 ? "Well-calibrated" : uncertainty < 15 ? "Moderate" : "High uncertainty"} />
            <KVRow label="Method" value={data.elementData?.uncertainty_method || data.hypothesisData?.uncertainty_method || "Bayesian"} />
          </div>
        </div>
      )}

      <Divider />

      <div>
        <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">Limitations</h4>
        <div className="space-y-2">
          {data.elementData?.limitations?.map((lim: string, i: number) => (
            <LimitationRow key={i} text={lim} />
          )).length || (
            data.hypothesisData?.limitations?.map((lim: string, i: number) => (
              <LimitationRow key={i} text={lim} />
            )).length || (
              <div className="text-sm text-[var(--color-fg-muted)] text-center py-4">No limitations recorded</div>
            )
          )}
        </div>
      </div>

      <Divider />

      <div>
        <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">Validation</h4>
        <div className="space-y-1">
          <KVRow label="Cross-validated" value={data.elementData?.cross_validated ? "Yes" : "No"} />
          <KVRow label="Peer reviewed" value={data.elementData?.peer_reviewed ? "Yes" : "No"} />
          <KVRow label="Reproducibility" value={data.elementData?.reproducibility_score ? `${data.elementData.reproducibility_score}%` : "Not tested"} />
        </div>
      </div>
    </div>
  );
}

function RelatedPanel({ data }: { data: InspectorData }) {
  if (!data.mode) return <EmptyState message="No element selected" />;

  const related = {
    nodes: data.elementData?.related_nodes || [],
    edges: data.elementData?.related_edges || [],
    evidence: data.elementData?.related_evidence || data.hypothesisData?.supporting_evidence || data.hypothesisData?.contradicting_evidence || [],
    hypotheses: data.elementData?.related_hypotheses || data.evidenceData?.related_hypotheses || [],
    experiments: data.hypothesisData?.related_experiments || [],
    patches: data.hypothesisData?.candidate_patches || [],
  };

  const hasAny = Object.values(related).some((arr) => arr.length > 0);

  if (!hasAny) return <EmptyState message="No related entities" />;

  return (
    <div className="space-y-4">
      {related.nodes.length > 0 && (
        <EntityGroup title="Related Nodes" count={related.nodes.length} icon={<Zap className="h-3.5 w-3.5" />}>
          {related.nodes.map((node: any, i: number) => (
            <EntityRow key={i} entity={node} type="node" />
          ))}
        </EntityGroup>
      )}

      {related.edges.length > 0 && (
        <>
          <Divider />
          <EntityGroup title="Related Edges" count={related.edges.length} icon={<LinkIcon className="h-3.5 w-3.5" />}>
            {related.edges.map((edge: any, i: number) => (
              <EntityRow key={i} entity={edge} type="edge" />
            ))}
          </EntityGroup>
        </>
      )}

      {related.evidence.length > 0 && (
        <>
          <Divider />
          <EntityGroup title="Related Evidence" count={related.evidence.length} icon={<Database className="h-3.5 w-3.5" />}>
            {related.evidence.map((ev: any, i: number) => (
              <EntityRow key={i} entity={ev} type="evidence" />
            ))}
          </EntityGroup>
        </>
      )}

      {related.hypotheses.length > 0 && (
        <>
          <Divider />
          <EntityGroup title="Related Hypotheses" count={related.hypotheses.length} icon={<Shield className="h-3.5 w-3.5" />}>
            {related.hypotheses.map((hyp: any, i: number) => (
              <EntityRow key={i} entity={hyp} type="hypothesis" />
            ))}
          </EntityGroup>
        </>
      )}

      {related.experiments.length > 0 && (
        <>
          <Divider />
          <EntityGroup title="Related Experiments" count={related.experiments.length} icon={<Search className="h-3.5 w-3.5" />}>
            {related.experiments.map((exp: any, i: number) => (
              <EntityRow key={i} entity={exp} type="experiment" />
            ))}
          </EntityGroup>
        </>
      )}

      {related.patches.length > 0 && (
        <>
          <Divider />
          <EntityGroup title="Candidate Patches" count={related.patches.length} icon={<Eye className="h-3.5 w-3.5" />}>
            {related.patches.map((patch: any, i: number) => (
              <EntityRow key={i} entity={patch} type="patch" />
            ))}
          </EntityGroup>
        </>
      )}
    </div>
  );
}

function EvidencePanel({ data }: { data: InspectorData }) {
  if (!data.mode) return <EmptyState message="No element selected" />;

  const supporting = data.hypothesisData?.supporting_evidence || [];
  const contradicting = data.hypothesisData?.contradicting_evidence || [];
  const evidenceItems = data.evidenceData ? [data.evidenceData] : data.elementData?.related_evidence || [];

  return (
    <div className="space-y-4">
      {supporting.length > 0 && (
        <div>
          <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2 flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success-emphasis)]" />
            Supporting Evidence ({supporting.length})
          </h4>
          <div className="space-y-2">
            {supporting.map((ev: any, i: number) => (
              <EvidenceRow key={i} evidence={ev} stance="supporting" />
            ))}
          </div>
        </div>
      )}

      {contradicting.length > 0 && (
        <>
          <Divider />
          <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2 flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-danger-emphasis)]" />
            Contradicting Evidence ({contradicting.length})
          </h4>
          <div className="space-y-2">
            {contradicting.map((ev: any, i: number) => (
              <EvidenceRow key={i} evidence={ev} stance="contradicting" />
            ))}
          </div>
        </>
      )}

      {evidenceItems.length > 0 && (!supporting.length && !contradicting.length) && (
        <div>
          <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2">
            Evidence Items
          </h4>
          <div className="space-y-2">
            {evidenceItems.map((ev: any, i: number) => (
              <EvidenceRow key={i} evidence={ev} stance="neutral" />
            ))}
          </div>
        </div>
      )}

      {!supporting.length && !contradicting.length && !evidenceItems.length && (
        <EmptyState message="No evidence linked to this element" />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Helper Components                                                          */
/* -------------------------------------------------------------------------- */

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[200px] gap-4 text-center px-6">
      <Search className="h-10 w-10 text-[var(--color-fg-muted)]/50" />
      <span className="text-[var(--color-fg-muted)]">{message}</span>
    </div>
  );
}

function ArtifactRow({ artifact }: { artifact: any }) {
  return (
    <div className="p-2 rounded-[var(--radius-md)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-xs font-medium text-[var(--color-fg-default)] truncate">{artifact.name || artifact.id}</span>
        <Badge variant="muted" className="text-[10px]">{artifact.type}</Badge>
      </div>
      <div className="flex items-center gap-2 text-[11px] text-[var(--color-fg-muted)]">
        <span className="font-mono">{artifact.checksum?.slice(0, 16)}…</span>
        {artifact.size && <span>{formatBytes(artifact.size)}</span>}
        {artifact.timestamp && <span>{formatTimestamp(artifact.timestamp)}</span>}
      </div>
    </div>
  );
}

function LineageStep({ step }: { step: any }) {
  return (
    <div className="flex items-start gap-2 p-2 rounded-[var(--radius-md)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]">
      <div className="flex h-6 w-6 items-center justify-center rounded bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)] text-xs font-mono">
        {step.order || "?"}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-[var(--color-fg-default)] truncate">{step.operation || step.transform}</div>
        <div className="text-[11px] text-[var(--color-fg-muted)] truncate">{step.input} → {step.output}</div>
        {step.timestamp && <div className="text-[10px] text-[var(--color-fg-subtle)]">{formatTimestamp(step.timestamp)}</div>}
      </div>
    </div>
  );
}

function KVRow({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 text-sm">
      <div className="flex-1 min-w-0">
        <span className="text-[var(--color-fg-muted)]">{label}</span>
        {sub && <span className="block text-[11px] text-[var(--color-fg-subtle)]">{sub}</span>}
      </div>
      <div className="text-right font-medium text-[var(--color-fg-default)] flex-shrink-0">
        {value}
      </div>
    </div>
  );
}

function LimitationRow({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 p-2 rounded-[var(--radius-md)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]">
      <AlertTriangle className="h-4 w-4 text-[var(--color-attention-emphasis)] flex-shrink-0 mt-0.5" />
      <span className="text-sm text-[var(--color-fg-default)]/80">{text}</span>
    </div>
  );
}

function EntityGroup({ title, count, icon, children }: { title: string; count: number; icon: ReactNode; children: ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] mb-2 flex items-center gap-1.5">
        {icon}
        {title} ({count})
      </h4>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function EntityRow({ entity, type }: { entity: any; type: string }) {
  const typeConfig = {
    node: { icon: Zap, color: "text-[var(--color-accent-fg)]" },
    edge: { icon: LinkIcon, color: "text-[var(--color-fg-muted)]" },
    evidence: { icon: Database, color: "text-[var(--color-success-fg)]" },
    hypothesis: { icon: Shield, color: "text-[var(--color-accent-fg)]" },
    experiment: { icon: Search, color: "text-[var(--color-fg-muted)]" },
    patch: { icon: Eye, color: "text-[var(--color-success-fg)]" },
  };
  const config = typeConfig[type as keyof typeof typeConfig] || typeConfig.node;

  return (
    <Tooltip content="Open in detail view" position="right">
      <button
        className="w-full flex items-center gap-2 p-2 rounded-[var(--radius-md)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors text-left"
        onClick={() => console.log(`Navigate to ${type}:`, entity.id)}
      >
        <config.icon className={`h-4 w-4 ${config.color}`} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-[var(--color-fg-default)] truncate">{entity.label || entity.id}</div>
          <div className="text-[10px] text-[var(--color-fg-muted)] truncate">{entity.type || type}</div>
        </div>
        <ExternalLink className="h-3.5 w-3.5 text-[var(--color-fg-subtle)]/50" />
      </button>
    </Tooltip>
  );
}

function EvidenceRow({ evidence, stance }: { evidence: any; stance: "supporting" | "contradicting" | "neutral" }) {
  const stanceConfig = {
    supporting: { badge: "success", label: "Supports" },
    contradicting: { badge: "danger", label: "Contradicts" },
    neutral: { badge: "muted", label: "Related" },
  };
  const config = stanceConfig[stance];

  return (
    <Tooltip content="View evidence details" position="right">
      <button
        className="w-full flex items-start gap-2 p-2 rounded-[var(--radius-md)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors text-left"
        onClick={() => console.log("Open evidence:", evidence.id)}
      >
        <div className="flex h-6 w-6 items-center justify-center rounded bg-[var(--color-canvas-subtle)]">
          {stance === "supporting" && <Check className="h-3.5 w-3.5 text-[var(--color-success-fg)]" />}
          {stance === "contradicting" && <X className="h-3.5 w-3.5 text-[var(--color-danger-fg)]" />}
          {stance === "neutral" && <div className="h-2 w-2 rounded-full bg-[var(--color-fg-muted)]" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-[var(--color-fg-default)] truncate">{evidence.name || evidence.id}</span>
            <Badge variant={config.badge as any} className="text-[10px]">{config.label}</Badge>
          </div>
          <div className="text-[11px] text-[var(--color-fg-muted)] truncate">{evidence.type}</div>
          {evidence.confidence !== undefined && (
            <div className="text-[10px] text-[var(--color-fg-subtle)]">Confidence: {Math.round(evidence.confidence * 100)}%</div>
          )}
        </div>
      </button>
    </Tooltip>
  );
}

/* -------------------------------------------------------------------------- */
/* Utilities                                                                  */
/* -------------------------------------------------------------------------- */

function getModeIcon(mode: InspectorMode): ReactNode {
  if (!mode) return <FileText className="h-5 w-5" />;
  const icons: Record<Exclude<InspectorMode, null>, ReactNode> = {
    timeline: <Clock className="h-5 w-5" />,
    graph: <GitBranch className="h-5 w-5" />,
    evidence: <Database className="h-5 w-5" />,
    hypothesis: <Shield className="h-5 w-5" />,
    experiment: <FlaskConical className="h-5 w-5" />,
    patch: <Wrench className="h-5 w-5" />,
  };
  return icons[mode] || <FileText className="h-5 w-5" />;
}

function getModeLabel(mode: InspectorMode): string {
  if (!mode) return "Inspector";
  const labels: Record<Exclude<InspectorMode, null>, string> = {
    timeline: "Timeline Event",
    graph: "Graph Element",
    evidence: "Evidence Item",
    hypothesis: "Hypothesis",
    experiment: "Experiment",
    patch: "Patch Candidate",
  };
  return labels[mode] || "Inspector";
}

function getModeDescription(mode: InspectorMode, data: InspectorData): string {
  switch (mode) {
    case "timeline":
      return data.eventData?.type || "Event details";
    case "graph":
      return data.elementType === "edge" ? "Edge relationship" : "Node entity";
    case "evidence":
      return data.evidenceData?.type || "Artifact";
    case "hypothesis":
      return data.hypothesisData?.type || "Causal claim";
    case "experiment":
      return data.experimentData?.type || "Simulation trial";
    case "patch":
      return data.patchData?.type || "Code fix";
    default:
      return "";
  }
}

function formatTimestamp(ts: string | number): string {
  const date = new Date(typeof ts === "number" ? ts : Date.parse(ts));
  if (isNaN(date.getTime())) return "Invalid date";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 80) return "var(--color-success-emphasis)";
  if (confidence >= 60) return "var(--color-attention-emphasis)";
  return "var(--color-danger-emphasis)";
}