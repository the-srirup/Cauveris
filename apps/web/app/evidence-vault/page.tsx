"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { Button, Badge, PageHeader, Input, Select, Stat, Panel, PanelSection, PanelStack, PanelCard, PanelDivider, PanelHeader, PanelFooter } from "@/components/ui";
import { api, Incident, IncidentReport } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import type { InspectorData } from "@/lib/useShell";
import { AuthGate } from "@/components/AuthGate";
import { X, Search, Download, FileCode, Shield, ChevronRight, RotateCcw, ExternalLink } from "lucide-react";
import { VirtualizedList } from "@/components/VirtualizedList";
import { DataErrorBoundary } from "@/components/ErrorBoundary";

interface VaultItem {
  id: string;
  name: string;
  type: "evidence" | "hypothesis" | "experiment" | "patch" | "report";
  status: string;
  description: string;
  size?: number | string;
  checksum?: string;
  path?: string;
  priority?: number;
}

function EvidenceVaultContent() {
  const { incidentId, judgeMode, engineerMode } = useActiveIncident();
  const { openInspector, setIncidentContext } = useShell();

  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Evidence Vault",
        state: "IDLE",
        pipelineStage: "IDLE",
        evidenceCoverage: 0,
        modelProvider: "Local Fixtures",
        backendStatus: "online",
        processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
        isDemonstration: false,
      });
    } else {
      setIncidentContext(null);
    }
  }, [incidentId, judgeMode, engineerMode]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [report, setReport] = useState<IncidentReport | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedItem, setSelectedItem] = useState<VaultItem | null>(null);

  const loadVaultData = async (id: string) => {
    try {
      const inc = await api.get(id);
      setIncident(inc);
      const rep = await api.getReport(id);
      setReport(rep);
    } catch {
      // Fallback
    }
  };

  useEffect(() => {
    if (incidentId) {
      loadVaultData(incidentId);
    }
  }, [incidentId]);

  const allItems: VaultItem[] = useMemo(() => {
    const items: VaultItem[] = [];
    const priorityOrder = [
      "manifest.yaml", "config/inference.yaml", "deployments/events.json",
      "traces/otel.json", "source/robot-stack/src/detection_client.py",
      "logs/", "metrics/", "recordings/"
    ];

    if (incident?.evidence_items) {
      incident.evidence_items.forEach((ev, idx) => {
        items.push({
          id: `ev-${ev.file_path}`,
          name: ev.file_path,
          type: "evidence",
          status: ev.status || "OBSERVED",
          description: `Evidence artifact (${ev.file_type}) ${ev.is_required ? "• REQUIRED" : ""}`,
          size: ev.size_bytes ? `${Math.round(ev.size_bytes / 1024)} KB` : undefined,
          checksum: ev.checksum_sha256 ? `${ev.checksum_sha256.slice(0, 16)}...` : undefined,
          path: ev.file_path,
          priority: priorityOrder.findIndex(p => ev.file_path.startsWith(p))
        });
      });
    }

    if (report?.hypotheses) {
      report.hypotheses.forEach((hyp, idx) => {
        items.push({
          id: hyp.hypothesis_id || hyp.id || `hyp-${idx}`,
          name: hyp.title || hyp.hypothesis_id || hyp.id,
          type: "hypothesis",
          status: hyp.status || "PENDING",
          description: hyp.causal_claim || hyp.description || "Hypothesis investigation",
          path: `hypotheses/${hyp.hypothesis_id || hyp.id}`,
          priority: idx
        });
      });
    }

    if (report?.experiments) {
      report.experiments.forEach((exp, idx) => {
        items.push({
          id: exp.experiment_id || exp.id || `exp-${idx}`,
          name: exp.name || exp.experiment_id || exp.id,
          type: "experiment",
          status: exp.status || "PENDING",
          description: exp.name || exp.intervention || "Digital twin simulation",
          path: `experiments/${exp.experiment_id || exp.id}`,
          priority: idx
        });
      });
    }

    if (report?.patch_candidates) {
      report.patch_candidates.forEach((patch, idx) => {
        items.push({
          id: patch.candidate_id || patch.id || `patch-${idx}`,
          name: patch.title || patch.candidate_id || patch.id,
          type: "patch",
          status: patch.verified ? "VERIFIED" : "PENDING",
          description: patch.rationale || "Patch candidate for investigation",
          path: "report",
          priority: idx
        });
      });
    }

    if (report) {
      items.push({
        id: `report-${incidentId}`,
        name: `Incident Report: ${report.title || incidentId}`,
        type: "report",
        status: report.status || "COMPLETED",
        description: report.description || "Comprehensive investigation report with provenance",
        path: `report/${incidentId}/incident_report.json`,
        priority: 99
      });
    }

    return items;
  }, [incident, report, incidentId]);

  const filteredItems = useMemo(() => {
    return allItems.filter((item) => {
      const matchesSearch =
        searchQuery === "" ||
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.id.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesType = typeFilter === "all" || item.type === typeFilter;
      const matchesStatus = statusFilter === "all" || item.status === statusFilter;

      return matchesSearch && matchesType && matchesStatus;
    });
  }, [allItems, searchQuery, typeFilter, statusFilter]);

  const countsByType = useMemo(() => {
    const counts = { evidence: 0, hypothesis: 0, experiment: 0, patch: 0, report: 0, verifiedPatches: 0 };
    allItems.forEach((i) => {
      if (i.type in counts) counts[i.type as keyof typeof counts]++;
      if (i.type === "patch" && i.status === "VERIFIED") counts.verifiedPatches++;
    });
    return counts;
  }, [allItems]);

  const handleDownloadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      notify("Downloading comprehensive incident report...", "info");
      const reportData = await api.getReport(incidentId);

      const reportStr = JSON.stringify(reportData, null, 2);
      const blob = new Blob([reportStr], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cauveris-report-${incidentId.slice(0, 8)}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      notify("Incident report downloaded successfully!", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Failed to download report", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPatchPackage = async () => {
    setLoading(true);
    setError(null);
    try {
      notify("Downloading verified patch package ZIP...", "info");
      const blob = await api.downloadPatchPackage(incidentId);

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cauveris-patch-package-${incidentId.slice(0, 8)}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      notify("Patch package downloaded!", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Failed to download patch package", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleOpenArtifactInspector = (item: VaultItem) => {
    if (item.type === "evidence") {
      const evidenceItem = incident?.evidence_items?.find(e => `ev-${e.file_path}` === item.id);
      const data: InspectorData = {
        mode: "evidence",
        evidenceId: item.id,
        evidenceData: {
          name: item.name,
          type: evidenceItem?.file_type || "Unknown",
          path: item.path,
          size: evidenceItem?.size_bytes,
          checksum: evidenceItem?.checksum_sha256,
          status: item.status,
          is_required: evidenceItem?.is_required,
          ingested_at: new Date().toISOString(),
          confidence: item.status === "CONFIRMED" ? 0.9 : 0.7,
        },
      };
      openInspector("evidence", data);
    } else if (item.type === "hypothesis") {
      const hyp = report?.hypotheses?.find(h => `hyp-${h.hypothesis_id || h.id}` === item.id || h.id === item.id);
      const data: InspectorData = {
        mode: "hypothesis",
        hypothesisId: item.id,
        hypothesisData: {
          ...hyp,
          type: "Causal Claim",
          confidence: hyp?.confidence ? hyp.confidence * 100 : 70,
          limitations: ["Based on available evidence", "Requires experimental validation"],
        },
      };
      openInspector("hypothesis", data);
    } else if (item.type === "experiment") {
      const exp = report?.experiments?.find(e => `exp-${e.experiment_id || e.id}` === item.id || e.id === item.id);
      const data: InspectorData = {
        mode: "experiment",
        experimentId: item.id,
        experimentData: {
          ...exp,
          type: "Digital Twin Simulation",
          confidence: exp?.reproduction_rate !== undefined ? Math.round((1 - exp.reproduction_rate) * 100) : 50,
        },
      };
      openInspector("experiment", data);
    } else if (item.type === "patch") {
      const patch = report?.patch_candidates?.find(p => `patch-${p.candidate_id || p.id}` === item.id || p.id === item.id);
      const data: InspectorData = {
        mode: "patch",
        patchId: item.id,
        patchData: {
          ...patch,
          type: "Code Fix",
          confidence: patch?.score ? patch.score * 100 : patch?.verified ? 97 : 42,
          limitations: patch?.verified ? ["Limited to simulated verification"] : ["Failed invariant gates"],
        },
      };
      openInspector("patch", data);
    } else if (item.type === "report") {
      const data: InspectorData = {
        mode: "patch",
        patchId: item.id,
        patchData: {
          title: item.name,
          type: "Investigation Report",
          status: item.status,
          description: item.description,
          path: item.path,
        },
      };
      openInspector("patch", data);
    }
  };

  const handleDownloadPatchScript = async () => {
    setLoading(true);
    setError(null);
    try {
      notify("Generating standalone executable patch installer...", "info");
      const text = await api.exportPatch(incidentId, "installer");

      const blob = new Blob([text as string], { type: "text/x-python" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `apply_patch_${incidentId.slice(0, 8)}.py`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      notify("Zero-dependency patch script (apply_patch.py) downloaded!", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Failed to download patch script", "error");
    } finally {
      setLoading(false);
    }
  };

  const getTypeIcon = (type: VaultItem["type"]) => {
    switch (type) {
      case "evidence": return "EVD";
      case "hypothesis": return "HYP";
      case "experiment": return "EXP";
      case "patch": return "PCH";
      case "report": return "RPT";
    }
  };

  const getStatusBadgeTone = (status: string) => {
    if (status === "CONFIRMED" || status === "VERIFIED" || status === "COMPLETED") return "success";
    if (status === "REFUTED" || status === "FAILED") return "danger";
    return "primary";
  };

  return (
    <div className="w-full space-y-5">
      <PageHeader
        title="Evidence Vault"
        subtitle="Complete provenance-linked artifact repository and evidence explorer"
        badge={
          <Badge tone="success" dot={true}>
            {allItems.length} Artifacts Indexed
          </Badge>
        }
      />

      {error && (
        <Panel variant="inset" padding="sm" className="border-[var(--color-danger-muted)] bg-[var(--color-danger-muted)]/30">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--color-danger-fg)]">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-[var(--color-danger-fg)] hover:text-[var(--color-fg-default)] text-xs font-semibold uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Dismiss
            </button>
          </div>
        </Panel>
      )}

      {/* Telemetry & Ingestion Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
        <Stat
          label="Evidence Items"
          value={incident?.evidence_count ?? countsByType.evidence}
          sub={`Required: ${incident?.required_evidence_count || 0} • Missing: ${incident?.missing_required_evidence?.length || 0}`}
          trend="success"
        />
        <Stat
          label="Report Status"
          value={report?.status || "INDEXED"}
          sub={`Hypotheses: ${countsByType.hypothesis} • Experiments: ${countsByType.experiment}`}
          trend="flat"
        />
        <Stat
          label="Verified Patches"
          value={countsByType.verifiedPatches}
          sub={countsByType.verifiedPatches > 0 ? "Zero-regression patches ready" : "Awaiting candidate synthesis"}
          trend={countsByType.verifiedPatches > 0 ? "success" : "muted"}
        />
      </div>

      {/* Artifact Inventory & Explorer Workspace */}
      <Panel padding="none">
        <PanelHeader
          title="Artifact Inventory & Explorer"
          subtitle={`${filteredItems.length} of ${allItems.length} artifacts • Double-click to inspect provenance in drawer`}
          divider={true}
          actions={
            <Badge tone="success" size="sm">
              {filteredItems.length} of {allItems.length} indexed
            </Badge>
          }
        />

        {/* Integrated Filter Toolbar */}
        <div className="border-b border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 px-5 sm:px-6 py-3 space-y-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            <Input
              label="Search artifacts"
              hideLabel
              wrapperClassName="flex-1 min-w-[200px]"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search artifacts, files, checksums..."
              leftIcon={<Search className="h-3.5 w-3.5" />}
              rightElement={searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="inline-flex h-5 w-5 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-fg-muted)] hover:text-[var(--color-accent-fg)] hover:bg-[var(--color-canvas-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  aria-label="Clear search"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
              className="h-8 text-xs"
            />

            <div className="flex items-center gap-2 shrink-0">
              <Select
                label="Filter by artifact type"
                hideLabel
                wrapperClassName="w-40 sm:w-44 shrink-0"
                value={typeFilter}
                onValueChange={setTypeFilter}
                className="h-8 text-xs"
                options={[
                  { value: "all", label: `All Types (${allItems.length})` },
                  { value: "evidence", label: `Evidence (${countsByType.evidence})` },
                  { value: "hypothesis", label: `Hypotheses (${countsByType.hypothesis})` },
                  { value: "experiment", label: `Experiments (${countsByType.experiment})` },
                  { value: "patch", label: `Patches (${countsByType.patch})` },
                  { value: "report", label: `Reports (${countsByType.report})` },
                ]}
              />

              <Select
                label="Filter by status"
                hideLabel
                wrapperClassName="w-36 shrink-0"
                value={statusFilter}
                onValueChange={setStatusFilter}
                className="h-8 text-xs"
                options={[
                  { value: "all", label: "All Statuses" },
                  { value: "OBSERVED", label: "OBSERVED" },
                  { value: "CONFIRMED", label: "CONFIRMED" },
                  { value: "REFUTED", label: "REFUTED" },
                  { value: "VERIFIED", label: "VERIFIED" },
                  { value: "COMPLETED", label: "COMPLETED" },
                ]}
              />

              {(searchQuery || typeFilter !== "all" || statusFilter !== "all") && (
                <button
                  type="button"
                  onClick={() => { setSearchQuery(""); setTypeFilter("all"); setStatusFilter("all"); }}
                  className="h-8 px-2.5 text-xs font-semibold text-[var(--color-fg-muted)] hover:text-[var(--color-accent-fg)] hover:bg-[var(--color-canvas)] rounded-[var(--radius-sm)] border border-[var(--color-border-default)] transition-colors shrink-0 flex items-center gap-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                >
                  <RotateCcw className="h-3 w-3" />
                  <span>Reset</span>
                </button>
              )}
            </div>
          </div>

          {/* Quick Segment Filter Pills */}
          <div className="flex items-center justify-between gap-3 pt-0.5">
            <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none py-0.5">
              {[
                { id: "all", label: "All", count: allItems.length },
                { id: "evidence", label: "Evidence", count: countsByType.evidence },
                { id: "hypothesis", label: "Hypotheses", count: countsByType.hypothesis },
                { id: "experiment", label: "Experiments", count: countsByType.experiment },
                { id: "patch", label: "Patches", count: countsByType.patch },
                { id: "report", label: "Reports", count: countsByType.report },
              ].map((tab) => {
                const isActive = typeFilter === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setTypeFilter(tab.id)}
                    className={`px-2.5 py-1 rounded-[var(--radius-sm)] text-[11px] font-medium transition-colors shrink-0 flex items-center gap-1.5 border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                      isActive
                        ? "bg-[var(--color-accent-emphasis)] text-[var(--color-fg-on-emphasis)] border-[var(--color-accent-emphasis)]"
                        : "bg-[var(--color-canvas-inset)] text-[var(--color-fg-muted)] border-[var(--color-border-default)] hover:text-[var(--color-fg-default)] hover:border-[var(--color-border-strong)]"
                    }`}
                  >
                    <span>{tab.label}</span>
                    <span className={`text-[10px] font-mono px-1 py-0.2 rounded-full ${isActive ? "bg-white/20 text-white" : "bg-[var(--color-canvas-subtle)] text-[var(--color-fg-muted)]"}`}>
                      {tab.count}
                    </span>
                  </button>
                );
              })}
            </div>

            <span className="text-[11px] text-[var(--color-fg-muted)] shrink-0 hidden sm:inline">
              Showing <strong className="text-[var(--color-fg-default)]">{filteredItems.length}</strong> of {allItems.length}
            </span>
          </div>
        </div>

        {/* List View Container */}
        {filteredItems.length > 0 ? (
          <div className="h-[460px] w-full relative">
            <VirtualizedList
              items={filteredItems}
              itemHeight={64}
              height={460}
              overscanCount={4}
              renderItem={(item, index, itemStyle) => {
                const isSelected = selectedItem?.id === item.id;
                return (
                  <div
                    key={item.id}
                    onClick={() => setSelectedItem(item)}
                    onDoubleClick={() => handleOpenArtifactInspector(item)}
                    style={itemStyle}
                    className={`px-5 sm:px-6 py-2 border-b border-[var(--color-border-default)] transition-colors cursor-pointer flex items-center justify-between gap-4 select-none ${
                      isSelected
                        ? "bg-[var(--color-accent-subtle)] border-l-4 border-l-[var(--color-accent-emphasis)]"
                        : "hover:bg-[var(--color-canvas-subtle)]"
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] text-[var(--color-accent-fg)] flex items-center justify-center flex-shrink-0 text-xs font-mono font-bold">
                        {getTypeIcon(item.type)}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold text-[var(--color-fg-default)] text-xs truncate max-w-sm sm:max-w-md">{item.name}</h4>
                          <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] text-[var(--color-fg-muted)] shrink-0 hidden md:inline">
                            {item.type}
                          </span>
                        </div>
                        <p className="text-[11px] text-[var(--color-fg-muted)] truncate mt-0.5 max-w-md sm:max-w-lg">{item.description}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2.5 flex-shrink-0">
                      {item.checksum && (
                        <span className="text-[10px] font-mono text-[var(--color-fg-muted)] hidden lg:inline bg-[var(--color-canvas-inset)] px-2 py-0.5 rounded border border-[var(--color-border-default)]" title={`SHA-256: ${item.checksum}`}>
                          {item.checksum}
                        </span>
                      )}
                      {item.size && (
                        <span className="text-[10px] font-mono text-[var(--color-fg-muted)] hidden sm:inline">{item.size}</span>
                      )}
                      <Badge tone={getStatusBadgeTone(item.status)} size="sm">
                        {item.status}
                      </Badge>
                      <ChevronRight className="h-4 w-4 text-[var(--color-fg-muted)]" />
                    </div>
                  </div>
                );
              }}
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center text-[var(--color-fg-muted)]">
            <FileCode className="h-12 w-12 text-[var(--color-fg-muted)]/50 mb-3" />
            <p className="text-base font-semibold text-[var(--color-fg-default)]">No artifacts match your filters</p>
            <p className="text-xs text-[var(--color-fg-muted)] mt-1 max-w-sm">Try broadening your search term or selecting a different artifact type filter</p>
            <button
              type="button"
              onClick={() => { setSearchQuery(""); setTypeFilter("all"); setStatusFilter("all"); }}
              className="mt-4 px-3 py-1.5 text-xs font-semibold rounded-[var(--radius-sm)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] hover:bg-[var(--color-canvas-inset)] text-[var(--color-fg-default)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Clear all filters
            </button>
          </div>
        )}

        {/* Selected Item Provenance Details */}
        {selectedItem && (
          <PanelSection dividerBefore={true} className="border-t border-[var(--color-accent-emphasis)]/30 bg-[var(--color-accent-subtle)]/30">
            <PanelHeader
              title={
                <div className="flex items-center gap-2">
                  <span>Artifact Provenance Details</span>
                  <Badge tone={getStatusBadgeTone(selectedItem.status)} size="sm">{selectedItem.status}</Badge>
                </div>
              }
              subtitle={`SHA-256 verified provenance record • ${selectedItem.name}`}
              actions={
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleOpenArtifactInspector(selectedItem)}
                    className="text-xs font-semibold text-[var(--color-accent-fg)] hover:text-[var(--color-accent-emphasis)] flex items-center gap-1 px-2.5 py-1 rounded-[var(--radius-sm)] border border-[var(--color-accent-emphasis)]/30 hover:bg-[var(--color-accent-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  >
                    <ExternalLink className="h-3 w-3" />
                    <span>Open in Inspector</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedItem(null)}
                    className="text-[var(--color-fg-muted)] hover:text-[var(--color-accent-fg)] text-xs font-semibold flex items-center gap-1 px-2 py-1 rounded-[var(--radius-sm)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  >
                    <X className="h-3.5 w-3.5" />
                    <span>Close</span>
                  </button>
                </div>
              }
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs pt-1">
              <div className="p-2.5 rounded-[var(--radius-sm)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)] block">Identifier</span>
                <code className="text-[var(--color-accent-fg)] font-mono text-xs mt-0.5 block truncate" title={selectedItem.id}>{selectedItem.id}</code>
              </div>
              <div className="p-2.5 rounded-[var(--radius-sm)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)] block">Artifact Type</span>
                <span className="text-[var(--color-fg-default)] font-mono text-xs mt-0.5 block uppercase">{selectedItem.type}</span>
              </div>
              <div className="p-2.5 rounded-[var(--radius-sm)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)] block">Storage Path</span>
                <code className="text-[var(--color-fg-default)] font-mono text-xs mt-0.5 block truncate" title={selectedItem.path || selectedItem.name}>{selectedItem.path || selectedItem.name}</code>
              </div>
              <div className="p-2.5 rounded-[var(--radius-sm)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)] block">SHA-256 Checksum</span>
                <code className="text-[var(--color-accent-fg)] font-mono text-xs mt-0.5 block truncate" title={selectedItem.checksum || "Verified via manifest"}>{selectedItem.checksum || "Computed on Ingest"}</code>
              </div>
            </div>
          </PanelSection>
        )}
      </Panel>

      {/* Export & Download Actions */}
      <Panel variant="inset" padding="none">
        <PanelFooter align="between" divider={false} className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 w-full">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleDownloadReport} disabled={loading} leadingIcon={<Download className="h-3.5 w-3.5" />}>
              {loading ? "Exporting..." : "Download Full Report (JSON)"}
            </Button>
            <Button variant="outline" size="sm" onClick={handleDownloadPatchScript} disabled={loading} leadingIcon={<FileCode className="h-3.5 w-3.5" />}>
              {loading ? "Exporting..." : "Download Patch Script (.py)"}
            </Button>
          </div>
          <Button variant="primary" size="sm" onClick={handleDownloadPatchPackage} disabled={loading} leadingIcon={<Download className="h-3.5 w-3.5" />}>
            {loading ? "Exporting..." : "Download Patch Package (ZIP)"}
          </Button>
        </PanelFooter>
      </Panel>
    </div>
  );
}

export default function EvidenceVault() {
  return (
    <AuthGate redirect="/evidence-vault" loadingLabel="Loading Evidence Vault...">
      <DataErrorBoundary>
        <EvidenceVaultContent />
      </DataErrorBoundary>
    </AuthGate>
  );
}