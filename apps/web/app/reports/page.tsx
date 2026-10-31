"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  PageHeader,
  Badge,
  Button,
  Divider,
  Select,
  Input,
  Panel,
  PanelSection,
  PanelStack,
  PanelHeader,
  PanelFooter,
  PanelCard,
} from "@/components/ui";
import { Tooltip } from "@/components/Tooltip";
import {
  FileText,
  Download,
  Eye,
  Trash2,
  Clock,
  Search,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Zap,
  Database,
  Check,
  X,
  ExternalLink,
  Shield,
  Plus,
  Sparkles,
} from "lucide-react";
import { tv } from "tailwind-variants";
import { api } from "@/lib/api";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import { AuthGate } from "@/components/AuthGate";

export interface Report {
  id: string;
  incident_id: string;
  title: string;
  generated_at: string;
  size_bytes: number;
  format: "json" | "md" | "pdf" | "html";
  status: "ready" | "generating" | "failed";
  type: "investigation" | "executive" | "technical" | "compliance";
}

/**
 * The nine invariant gates, in the order the verifier applies them.
 */
const INVARIANT_CHECKS: Array<{ key: string; label: string }> = [
  { key: "applies_cleanly", label: "Patch applies cleanly" },
  { key: "regression_test_fails_before", label: "Regression test fails before the fix" },
  { key: "regression_test_passes_after", label: "Regression test passes after the fix" },
  { key: "original_failure_not_reproduced", label: "Original failure is not reproduced" },
  { key: "existing_tests_pass", label: "Existing tests still pass" },
  { key: "safety_invariants_pass", label: "Safety invariants hold" },
  { key: "performance_within_budget", label: "Performance stays within budget" },
  { key: "forbidden_change_scan_passes", label: "Forbidden-change scan passes" },
  { key: "rollback_test_passes", label: "Rollback restores the original state" },
];

/**
 * Build the exported report's verification section from the server's own
 * verification records.
 *
 * This used to print two unconditional sentences - "All counterfactual
 * trials passed causal invariance checks" and "Verified and clean
 * application candidate generated" - whatever the pipeline actually
 * produced.  A report is evidence; a report that asserts something the
 * evidence does not contain is worse than no report at all.  So every claim
 * below is read off a real verification report, and an incident with no
 * verified patch says so.
 */
function buildVerificationSection(data: any): string {
  const verifications: any[] = Array.isArray(data?.verification_reports)
    ? data.verification_reports
    : [];
  const patches: any[] = Array.isArray(data?.patch_candidates) ? data.patch_candidates : [];
  const verified = verifications.filter((v) => v?.verified);

  const gateRows = (report: any) =>
    INVARIANT_CHECKS.map(
      (check) =>
        `<tr><td>${check.label}</td><td style="text-align:right; color:${
          report?.[check.key] ? "#f4f4f5" : "#71717a"
        };">${report?.[check.key] ? "PASS" : "FAIL"}</td></tr>`
    ).join("");

  if (verified.length === 0) {
    const reason = patches.length
      ? `${patches.length} patch candidate${patches.length === 1 ? "" : "s"} were produced, but none cleared all nine invariant gates.`
      : "No patch candidate could be derived for this incident.";
    return `<div class="section">
      <div class="section-title">Verification & Remediation</div>
      <div class="card">
        <p><strong>Patch Status:</strong> ${reason}</p>
        <p><strong>Remediation:</strong> No verified remediation is available for this incident.</p>
      </div>
    </div>`;
  }

  const report = verified[0];
  const passed = INVARIANT_CHECKS.filter((c) => report?.[c.key]).length;
  return `<div class="section">
    <div class="section-title">Verification & Remediation</div>
    <div class="card">
      <p><strong>Patch Status:</strong> Verified patch <code>${
        report?.patch_candidate_id || patches[0]?.candidate_id || "unknown"
      }</code> passed ${passed} of ${INVARIANT_CHECKS.length} invariant gates.</p>
      <p><strong>Remediation:</strong> A verified patch candidate is available for this incident.</p>
      <table class="table">
        <thead><tr><th>Invariant gate</th><th style="text-align:right;">Result</th></tr></thead>
        <tbody>${gateRows(report)}</tbody>
      </table>
    </div>
  </div>`;
}

export function ReportsPage() {
  return (
    <AuthGate redirect="/reports" loadingLabel="Loading reports...">
      <ReportsPageContent />
    </AuthGate>
  );
}

function ReportsPageContent() {
  const { incident, incidentId, setIncidentId, judgeMode, engineerMode } = useActiveIncident();
  const { addActivity, setIncidentContext, state: shellState } = useShell();

  const [incidentsList, setIncidentsList] = useState<Array<{ id: string; title?: string; system_name?: string }>>([]);

  // Fetch available incidents if needed to support incident selection.
  // NOTE: setIncidentId from useActiveIncident is a fresh function identity on
  // every render, so it must live in a ref — putting it in the deps array would
  // re-run this effect (and its setState) after every render, looping forever.
  const setIncidentIdRef = useRef(setIncidentId);
  useEffect(() => {
    setIncidentIdRef.current = setIncidentId;
  }, [setIncidentId]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const res = typeof api?.list === "function" ? await api.list() : null;
        const items = Array.isArray(res?.incidents) ? res.incidents : [];
        if (!mounted) return;
        setIncidentsList(items);
        const setId = setIncidentIdRef.current;
        if (!incidentId && items.length > 0 && typeof setId === "function") {
          setId(items[0].id);
        }
      } catch {
        // incident list is best-effort; the reports list below is authoritative
      }
    };
    load();
    return () => {
      mounted = false;
    };
  }, [incidentId]);

  useEffect(() => {
    const currentId = incidentId || incident?.id;
    if (currentId) {
      setIncidentContext({
        id: currentId,
        title: "Reports",
        state: "IDLE",
        pipelineStage: "IDLE",
        evidenceCoverage: 0,
        modelProvider: shellState.incidentContext?.modelProvider || "Nebius Token Factory",
        backendStatus: "online",
        processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
        isDemonstration: false,
      });
    } else {
      setIncidentContext(null);
    }
  }, [incidentId, incident?.id, judgeMode, engineerMode]);

  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [generating, setGenerating] = useState<string | null>(null);

  // Action states
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [viewingReport, setViewingReport] = useState<Report | null>(null);
  const [viewingReportData, setViewingReportData] = useState<any | null>(null);
  const [loadingViewData, setLoadingViewData] = useState(false);
  const [activeViewTab, setActiveViewTab] = useState<"summary" | "document" | "json">("summary");
  const [copiedJson, setCopiedJson] = useState(false);
  const [deletingReport, setDeletingReport] = useState<Report | null>(null);

  // Close modals on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (deletingReport) {
          setDeletingReport(null);
        } else if (viewingReport) {
          setViewingReport(null);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [deletingReport, viewingReport]);

  // Load reports on mount and when active incident changes
  useEffect(() => {
    let mounted = true;
    const currentId = incidentId || incident?.id;
    if (!currentId) {
      setReports([]);
      return;
    }

    const loadReports = async () => {
      setLoading(true);
      try {
        if (typeof api?.listReports === "function") {
          const res = await api.listReports(currentId);
          if (mounted && res && res.reports) {
            setReports(res.reports as Report[]);
            return;
          }
        }
      } catch (error) {
        console.warn("Failed to load reports:", error);
      } finally {
        if (mounted) setLoading(false);
      }
      if (mounted) setReports([]);
    };
    loadReports();
    return () => {
      mounted = false;
    };
  }, [incidentId, incident?.id]);

  const filteredReports = reports.filter((r) => {
    if (filterType !== "all" && r.type !== filterType) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      if (!r.title.toLowerCase().includes(q) && !r.id.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const handleGenerate = async (_type?: Report["type"]) => {
    const currentIncidentId = incidentId || incident?.id;
    if (!currentIncidentId) {
      addActivity({ type: "error", message: "Select an incident before generating a report", dismissible: true });
      return;
    }
    const reportType = _type || "investigation";
    setGenerating(reportType);
    addActivity({
      type: "system",
      message: `Generating ${reportType} report for ${currentIncidentId}...`,
      dismissible: true,
    });
    try {
      // Trigger reconstruction/investigation if needed, then generate reports
      try {
        if (typeof (api as any)?.reconstruct === "function") {
          await api.reconstruct(currentIncidentId).catch(() => {});
        }
      } catch {
        // ignore
      }

      // 1. Try on-demand report generation if available
      if (typeof (api as any)?.generateReport === "function") {
        try {
          const genRes = await (api as any).generateReport(currentIncidentId, reportType);
          if (genRes?.reports && genRes.reports.length > 0) {
            setReports(genRes.reports as Report[]);
            setGenerating(null);
            addActivity({
              type: "system",
              message: `Report generated successfully for ${currentIncidentId}`,
              dismissible: true,
            });
            return;
          }
        } catch {
          // Fallback to polling listReports
        }
      }

      // 3. Immediately query listReports
      const initialRes = await api.listReports(currentIncidentId);
      const initialList = (initialRes?.reports as Report[]) ?? [];
      setReports(initialList);

      if (initialList.length > 0) {
        addActivity({
          type: "system",
          message: `Report ready for ${currentIncidentId}`,
          dismissible: true,
        });
        setGenerating(null);
      } else {
        // 4. Background pipeline is still processing; poll listReports every 1s for up to 20s
        let attempts = 0;
        const maxAttempts = 20;
        const pollId = setInterval(async () => {
          attempts++;
          try {
            const polled = await api.listReports(currentIncidentId);
            if (polled?.reports && polled.reports.length > 0) {
              clearInterval(pollId);
              setReports(polled.reports as Report[]);
              setGenerating(null);
              addActivity({
                type: "system",
                message: `Investigation report generated for ${currentIncidentId}`,
                dismissible: true,
              });
              return;
            }
          } catch {
            // ignore network polling hiccups
          }
          if (attempts >= maxAttempts) {
            clearInterval(pollId);
            setGenerating(null);
            const finalCheck = await api.listReports(currentIncidentId).catch(() => null);
            setReports((finalCheck?.reports as Report[]) ?? []);
          }
        }, 1000);
      }
    } catch (error: any) {
      addActivity({
        type: "error",
        message: `Failed to generate report: ${error?.message || "Unknown error"}`,
        dismissible: true,
      });
      setGenerating(null);
    }
  };

  /**
   * Helper to fetch report payload from the backend. Throws when the report
   * has not been generated server-side — there is no client-side fallback.
   */
  const resolveReportData = useCallback(async (report: Report) => {
    const data = await api.getReport(report.incident_id);
    if (!data || typeof (data as { incident_id?: unknown }).incident_id !== "string") {
      throw new Error("Report not yet generated on the server — run the investigation pipeline first");
    }
    return data;
  }, []);

  /**
   * 1. EYE ICON: View Report
   */
  const handleViewReport = async (report: Report) => {
    setViewingReport(report);
    setLoadingViewData(true);
    setActiveViewTab("summary");
    setCopiedJson(false);
    try {
      const data = await resolveReportData(report);
      setViewingReportData(data);
    } catch (error: any) {
      setViewingReport(null);
      addActivity({ type: "error", message: error?.message || "Failed to load report data", dismissible: true });
    } finally {
      setLoadingViewData(false);
    }
  };

  /**
   * Helper to generate standalone printable HTML for HTML/PDF downloads
   */
  const generateHtmlDocument = (report: Report, data: any) => {
    const isDark = true;
    const verificationSection = buildVerificationSection(data);
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${report.title} - ${report.incident_id}</title>
  <style>
    @media print {
      body { background: #fff !important; color: #111 !important; }
      .no-print { display: none !important; }
      .container { max-width: 100% !important; margin: 0 !important; padding: 0 !important; }
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      color: ${isDark ? "#f4f4f5" : "#18181b"};
      background-color: ${isDark ? "#09090b" : "#ffffff"};
      margin: 0;
      padding: 40px 20px;
    }
    .container {
      max-width: 860px;
      margin: 0 auto;
      background: ${isDark ? "#121215" : "#f4f4f5"};
      border: 1px solid ${isDark ? "#27272a" : "#e4e4e7"};
      border-radius: 12px;
      padding: 36px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
    }
    .header {
      border-bottom: 2px solid ${isDark ? "#3f3f46" : "#d4d4d8"};
      padding-bottom: 20px;
      margin-bottom: 28px;
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      margin-right: 8px;
      background: ${isDark ? "#18181b" : "#e4e4e7"};
      color: ${isDark ? "#f4f4f5" : "#18181b"};
      border: 1px solid ${isDark ? "#27272a" : "#d4d4d8"};
    }
    .badge-success { background: rgba(255, 255, 255, 0.08); color: #f4f4f5; border-color: rgba(255, 255, 255, 0.25); }
    h1 { margin: 12px 0 6px 0; font-size: 28px; color: ${isDark ? "#f4f4f5" : "#18181b"}; }
    .meta { font-size: 14px; color: #a1a1aa; font-family: monospace; }
    .section { margin-top: 32px; }
    .section-title {
      font-size: 18px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: ${isDark ? "#f4f4f5" : "#18181b"};
      border-bottom: 1px solid ${isDark ? "#27272a" : "#e4e4e7"};
      padding-bottom: 8px;
      margin-bottom: 16px;
    }
    .card {
      background: ${isDark ? "#18181b" : "#ffffff"};
      border: 1px solid ${isDark ? "#27272a" : "#e4e4e7"};
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 14px;
    }
    .table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
    .table th, .table td { padding: 10px 14px; text-align: left; border-bottom: 1px solid ${isDark ? "#27272a" : "#e4e4e7"}; }
    .table th { background: ${isDark ? "#27272a" : "#e4e4e7"}; color: #a1a1aa; font-weight: 600; text-transform: uppercase; font-size: 12px; }
    pre {
      background: ${isDark ? "#0e0e11" : "#f4f4f5"};
      padding: 16px;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 13px;
      border: 1px solid ${isDark ? "#27272a" : "#e4e4e7"};
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <span class="badge badge-success">Status: ${data.status || "COMPLETED"}</span>
      <span class="badge">Type: ${report.type}</span>
      <span class="badge">Format: ${report.format.toUpperCase()}</span>
      <h1>${report.title}</h1>
      <div class="meta">
        Incident ID: ${report.incident_id} | Report ID: ${report.id} | Generated: ${new Date(report.generated_at).toLocaleString()}
      </div>
    </div>

    <div class="section">
      <div class="section-title">Incident Overview</div>
      <div class="card">
        <p><strong>System:</strong> ${data.system_name || "N/A"}</p>
        <p><strong>Approximate Time:</strong> ${data.approximate_time || "N/A"}</p>
        <p><strong>Description:</strong> ${data.description || "N/A"}</p>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Root Cause Hypotheses & Evidence</div>
      ${(data.hypotheses || []).map((h: any) => `
        <div class="card">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong>${h.hypothesis_id}: ${h.status}</strong>
            <span class="badge">${Math.round((h.confidence_posterior || h.confidence_prior || 0) * 100)}% Confidence</span>
          </div>
          <p style="margin-top:8px;">${h.causal_claim}</p>
        </div>
      `).join("") || '<div class="card"><p>No hypotheses were produced for this incident.</p></div>'}
    </div>

    ${verificationSection}

    <div class="section no-print" style="margin-top: 40px; text-align: right;">
      <button onclick="window.print()" style="padding: 10px 20px; background: ${isDark ? "#f4f4f5" : "#18181b"}; color: ${isDark ? "#09090b" : "#ffffff"}; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;">
        Print / Save to PDF
      </button>
    </div>
  </div>
</body>
</html>`;
  };

  /**
   * 2. DOWNLOAD ICON: Download Report
   */
  const handleDownload = async (report: Report) => {
    setDownloadingId(report.id);
    try {
      const data = await resolveReportData(report);
      let content = "";
      let mimeType = "application/json";
      let extension = "json";

      if (report.format === "md") {
        content = await api.getReportMarkdown(report.incident_id);
        mimeType = "text/markdown;charset=utf-8";
        extension = "md";
      } else if (report.format === "html") {
        content = generateHtmlDocument(report, data);
        mimeType = "text/html;charset=utf-8";
        extension = "html";
      } else if (report.format === "pdf") {
        // PDF printable document
        content = generateHtmlDocument(report, data);
        mimeType = "text/html;charset=utf-8";
        extension = "html"; // Can be printed to PDF directly
      } else {
        // JSON format
        content = JSON.stringify(data, null, 2);
        mimeType = "application/json;charset=utf-8";
        extension = "json";
      }

      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${report.id}_${report.incident_id}.${extension}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      addActivity({
        type: "system",
        message: `Downloaded ${report.title} (${report.id}.${extension})`,
        dismissible: true,
      });
    } catch (error: any) {
      console.error("Download failed:", error);
      addActivity({ type: "error", message: error?.message || `Download failed for ${report.title}`, dismissible: true });
    } finally {
      setDownloadingId(null);
    }
  };

  /**
   * 3. DELETE ICON: Confirm & Delete Report
   */
  const handleConfirmDelete = async () => {
    if (!deletingReport) return;
    const target = deletingReport;
    try {
      // Optimistically remove from state
      setReports((prev) => prev.filter((r) => r.id !== target.id));
      if (viewingReport?.id === target.id) {
        setViewingReport(null);
      }
      setDeletingReport(null);

      // Call backend API if incident exists
      if (target.incident_id) {
        api.deleteReport(target.incident_id, target.id).catch(() => {});
      }

      addActivity({
        type: "system",
        message: `Report ${target.id} (${target.title}) deleted successfully`,
        dismissible: true,
      });
    } catch (error) {
      addActivity({ type: "error", message: `Failed to delete report ${target.id}`, dismissible: true });
    }
  };

  const handleCopyJson = () => {
    if (!viewingReportData) return;
    navigator.clipboard.writeText(JSON.stringify(viewingReportData, null, 2));
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  // Everything below is derived from the loaded report payload only.  Nothing
  // is asserted that the server's verification records do not contain.
  const verifiedReport = Array.isArray(viewingReportData?.verification_reports)
    ? viewingReportData.verification_reports.find((v: any) => v?.verified)
    : undefined;
  const gatesPassed = verifiedReport
    ? INVARIANT_CHECKS.filter((c) => verifiedReport?.[c.key]).length
    : 0;
  const selectedPatchId =
    verifiedReport?.patch_candidate_id || viewingReportData?.selected_repair_id || null;
  const selectedPatch = Array.isArray(viewingReportData?.patch_candidates)
    ? viewingReportData.patch_candidates.find((p: any) => p?.candidate_id === selectedPatchId)
    : undefined;
  const missingEvidence: string[] =
    viewingReportData?.evidence_summary?.missing_required_evidence ?? [];

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const typeConfig = {
    investigation: { icon: Zap, label: "Investigation", color: "text-[var(--color-accent-fg)]" },
    executive: { icon: FileText, label: "Executive", color: "text-[var(--color-attention-fg)]" },
    technical: { icon: Database, label: "Technical", color: "text-[var(--color-success-fg)]" },
    compliance: { icon: AlertTriangle, label: "Compliance", color: "text-[var(--color-danger-fg)]" },
  };

  return (
    <div className="w-full space-y-5">
      <PageHeader
        title="Reports"
        subtitle="Generated investigation reports and exports"
        breadcrumbs={[{ label: "Overview", href: "/" }, { label: "Reports" }]}
        badge={
          <Badge tone="neutral">{reports.length} reports</Badge>
        }
        actions={
          <div className="flex items-center gap-[var(--space-2)]">
            <Button
              variant="outline"
              size="sm"
              onClick={() => reports[0] && handleDownload(reports[0])}
              disabled={reports.length === 0}
              className="gap-1.5 text-xs h-8"
              aria-label="Download full report"
            >
              <Download className="h-3.5 w-3.5" />
              Download Full Report
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => handleGenerate("investigation")}
              disabled={!!generating}
              className="gap-1.5 text-xs h-8"
              aria-label="Generate report"
            >
              <Zap className="h-3.5 w-3.5" />
              Generate Report
            </Button>
          </div>
        }
      />

      {/* Generate New Report Bar */}
      <Panel variant="inset" padding="md">
        <PanelSection dividerBefore={false} className="flex flex-col md:flex-row md:items-center justify-between gap-[var(--space-4)]">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div>
              <h2 className="font-semibold text-[var(--color-fg-default)] text-base">Generate New Report</h2>
              <p className="mt-0.5 text-xs text-[var(--color-fg-muted)]">
                Create an automated investigation report for {incidentId || incident?.id || "active incident"}
              </p>
            </div>
            {incidentsList.length > 0 && typeof setIncidentId === "function" && (
              <div className="flex items-center gap-2">
                <Select
                  id="incident-selector"
                  label="Incident"
                  hideLabel
                  value={incidentId || incident?.id || incidentsList[0]?.id || ""}
                  onValueChange={(val) => setIncidentId(val)}
                  className="h-8 text-xs min-w-[150px]"
                  options={incidentsList.map((inc) => ({
                    value: inc.id,
                    label: inc.id,
                  }))}
                />
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-[var(--space-2)]">
            {(["investigation", "executive", "technical", "compliance"] as const).map((type) => (
              <Button
                key={type}
                variant={generating === type ? "outline" : "primary"}
                size="sm"
                onClick={() => handleGenerate(type)}
                disabled={!!generating}
                className="whitespace-nowrap text-xs h-8"
              >
                {generating === type ? (
                  <>
                    <span className="flex h-3.5 w-3.5 animate-spin">
                      <svg className="h-3.5 w-3.5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
                    </span>
                    Generating...
                  </>
                ) : (
                  type.charAt(0).toUpperCase() + type.slice(1)
                )}
              </Button>
            ))}
          </div>
        </PanelSection>
      </Panel>

      {/* Reports Table & Integrated Toolbar */}
      <Panel padding="none">
        <PanelHeader
          title="Report Inventory"
          subtitle={`${filteredReports.length} of ${reports.length} reports indexed`}
          divider={true}
          actions={
            <div className="flex items-center gap-2">
              <Badge tone="success" dot size="sm">
                {reports.filter((r) => r.status === "ready").length} Ready
              </Badge>
            </div>
          }
        />

        {/* Integrated Filter Toolbar */}
        <div className="border-b border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 px-5 sm:px-6 py-3 space-y-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            <Input
              label="Search reports"
              hideLabel
              wrapperClassName="flex-1 min-w-[200px]"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search reports by title or ID..."
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
                id="report-type-filter"
                label="Filter by report type"
                hideLabel
                wrapperClassName="w-40 sm:w-44 shrink-0"
                value={filterType}
                onValueChange={setFilterType}
                className="h-8 text-xs"
                options={[
                  { value: "all", label: `All Types (${reports.length})` },
                  { value: "investigation", label: "Investigation" },
                  { value: "executive", label: "Executive" },
                  { value: "technical", label: "Technical" },
                  { value: "compliance", label: "Compliance" },
                ]}
              />

              {filterType !== "all" && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setFilterType("all")}
                  className="h-8 px-2 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                  title="Reset filter"
                >
                  Reset
                </Button>
              )}
            </div>
          </div>

          {/* Quick Filter Badges */}
          <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
            <span className="text-[11px] text-[var(--color-fg-muted)] mr-1">Quick Filter:</span>
            {(["all", "investigation", "executive", "technical", "compliance"] as const).map((type) => {
              const count = type === "all" ? reports.length : reports.filter((r) => r.type === type).length;
              const isSelected = filterType === type;
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => setFilterType(type)}
                  className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[var(--radius-sm)] text-[11px] font-medium border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                    isSelected
                      ? "bg-[var(--color-accent-muted)] border-[var(--color-accent-emphasis)] text-[var(--color-accent-fg)]"
                      : "bg-[var(--color-canvas)] border-[var(--color-border-default)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)]"
                  }`}
                >
                  <span className="capitalize">{type}</span>
                  <span className="font-mono text-[10px] opacity-75">({count})</span>
                </button>
              );
            })}
          </div>
        </div>

        <PanelSection dividerBefore={false} className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-[var(--space-12)]">
              <div className="flex h-8 w-8 animate-spin">
                <svg className="h-8 w-8 text-[var(--color-accent-fg)]" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
              </div>
            </div>
          ) : filteredReports.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-[var(--space-16)] px-[var(--space-6)] gap-[var(--space-4)] text-center text-[var(--color-fg-muted)]">
              <FileText className="h-12 w-12 text-[var(--color-fg-muted)]/50" />
              <span className="text-lg font-semibold text-[var(--color-fg-default)]">No reports found</span>
              <p className="text-sm max-w-md">
                {incidentId || incident?.id
                  ? `No investigation reports generated for ${incidentId || incident?.id} yet. Generate one now to review causal analysis, verification gates, and repair packages.`
                  : "Generate a new report or adjust your filters"}
              </p>
              {(incidentId || incident?.id) && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleGenerate("investigation")}
                  disabled={!!generating}
                  className="gap-1.5 text-xs h-8 mt-2"
                >
                  <Zap className="h-3.5 w-3.5" />
                  Generate Full Investigation Report
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="text-left text-[11px] font-medium uppercase tracking-wider text-[var(--color-fg-muted)] border-b border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/20">
                    <th className="py-2.5 px-5 sm:px-6 font-semibold">Report</th>
                    <th className="py-2.5 pr-4 hidden md:table-cell font-semibold">Incident</th>
                    <th className="py-2.5 pr-4 hidden lg:table-cell font-semibold">Type</th>
                    <th className="py-2.5 pr-4 hidden md:table-cell font-semibold">Format</th>
                    <th className="py-2.5 pr-4 font-semibold">Size</th>
                    <th className="py-2.5 pr-4 font-semibold">Generated</th>
                    <th className="py-2.5 pr-4 font-semibold">Status</th>
                    <th className="py-2.5 px-5 sm:px-6 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredReports.map((report) => {
                    const config = typeConfig[report.type] || typeConfig.investigation;
                    const isDownloading = downloadingId === report.id;
                    return (
                      <tr
                        key={report.id}
                        className="border-b border-[var(--color-border-default)] hover:bg-[var(--color-canvas-subtle)]/70 transition-colors cursor-pointer group"
                        onClick={() => handleViewReport(report)}
                        title="Click to view report details"
                      >
                        <td className="py-3 px-5 sm:px-6">
                          <div className="flex items-center gap-[var(--space-3)]">
                            <config.icon className={`h-5 w-5 ${config.color} flex-shrink-0`} />
                            <div>
                              <div className="font-medium text-[var(--color-fg-default)] truncate max-w-xs">{report.title}</div>
                              <div className="text-[11px] text-[var(--color-fg-muted)] font-mono">{report.id}</div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 pr-4 hidden md:table-cell">
                          <span className="font-mono text-xs text-[var(--color-fg-default)]">{report.incident_id}</span>
                        </td>
                        <td className="py-3 pr-4 hidden lg:table-cell">
                          <Badge
                            tone={
                              report.type === "investigation"
                                ? "primary"
                                : report.type === "executive"
                                ? "secondary"
                                : report.type === "technical"
                                ? "success"
                                : "danger"
                            }
                            className="text-[10px]"
                          >
                            {config.label}
                          </Badge>
                        </td>
                        <td className="py-3 pr-4 hidden md:table-cell">
                          <Badge tone="muted" className="text-[10px] font-mono uppercase">
                            {report.format.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="py-3 pr-4 font-mono text-xs text-[var(--color-fg-default)]">{formatBytes(report.size_bytes)}</td>
                        <td className="py-3 pr-4 text-xs text-[var(--color-fg-muted)]">{formatDate(report.generated_at)}</td>
                        <td className="py-3 pr-4">
                          <Badge
                            tone={
                              report.status === "ready"
                                ? "success"
                                : report.status === "generating"
                                ? "primary"
                                : "danger"
                            }
                            dot
                            className="text-[10px]"
                          >
                            {report.status.charAt(0).toUpperCase() + report.status.slice(1)}
                          </Badge>
                        </td>
                        <td className="py-3 px-5 sm:px-6 text-right">
                          <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                            {/* Eye / View Icon */}
                            <Tooltip content="View report" position="top">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleViewReport(report);
                                }}
                                className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)]"
                                aria-label={`View report ${report.title}`}
                                title={`View report ${report.title}`}
                              >
                                <Eye className="h-4 w-4" />
                              </button>
                            </Tooltip>

                            {/* Download Icon */}
                            <Tooltip content="Download report" position="top">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDownload(report);
                                }}
                                disabled={report.status !== "ready" || isDownloading}
                                className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)]"
                                aria-label={`Download report ${report.title}`}
                                title={`Download report ${report.title}`}
                              >
                                {isDownloading ? (
                                  <span className="flex h-4 w-4 animate-spin">
                                    <svg className="h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
                                  </span>
                                ) : (
                                  <Download className="h-4 w-4" />
                                )}
                              </button>
                            </Tooltip>

                            {/* Delete Icon */}
                            <Tooltip content="Delete report" position="top">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setDeletingReport(report);
                                }}
                                className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:text-[var(--color-danger-fg)] hover:bg-[var(--color-danger-muted)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-danger-fg)]"
                                aria-label={`Delete report ${report.title}`}
                                title={`Delete report ${report.title}`}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </Tooltip>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </PanelSection>
      </Panel>

      {/* Report Templates */}
      <Panel variant="inset" padding="md">
        <PanelHeader
          title="Report Templates"
          subtitle="Pre-configured report types for different audiences and compliance requirements"
          divider={true}
        />
        <PanelSection dividerBefore={false} className="grid gap-[var(--space-4)] md:grid-cols-2 lg:grid-cols-4 items-stretch">
          {[
            { type: "investigation", name: "Full Investigation", desc: "Complete pipeline trace with all evidence, hypotheses, and verdicts", icon: Zap },
            { type: "executive", name: "Executive Summary", desc: "High-level findings, risk assessment, and recommended actions", icon: FileText },
            { type: "technical", name: "Technical Deep Dive", desc: "Detailed causal analysis, graph metrics, and experiment logs", icon: Database },
            { type: "compliance", name: "Compliance Report", desc: "Regulatory compliance mapping with audit trail", icon: AlertTriangle },
          ].map((tmpl, i) => (
            <div
              key={i}
              role="button"
              tabIndex={0}
              onClick={() => handleGenerate(tmpl.type as Report["type"])}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleGenerate(tmpl.type as Report["type"]);
                }
              }}
              className="group relative flex flex-col justify-between h-full min-h-[120px] p-4 bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] rounded-[var(--radius-md)] hover:bg-[var(--color-canvas-subtle)] hover:border-[var(--color-border-default)]/80 cursor-pointer transition-colors duration-100 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)]"
              aria-label={`Generate ${tmpl.name}`}
            >
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-canvas-subtle)] text-[var(--color-accent-fg)] border border-[var(--color-border-default)]">
                  <tmpl.icon className="h-4.5 w-4.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <h3 className="text-xs font-semibold text-[var(--color-fg-default)] truncate">{tmpl.name}</h3>
                    <Plus className="h-3.5 w-3.5 shrink-0 text-[var(--color-fg-muted)] group-hover:text-[var(--color-accent-fg)] transition-colors" />
                  </div>
                  <p className="text-[11px] text-[var(--color-fg-muted)] mt-1.5 leading-relaxed line-clamp-3">{tmpl.desc}</p>
                </div>
              </div>
              <div className="mt-3 pt-2.5 border-t border-[var(--color-border-default)]/60 flex items-center justify-between text-[10px] text-[var(--color-fg-subtle)]">
                <span className="font-mono uppercase">{tmpl.type}</span>
                <span className="text-[var(--color-accent-fg)] opacity-0 group-hover:opacity-100 transition-opacity font-medium">Click to generate →</span>
              </div>
            </div>
          ))}
        </PanelSection>
      </Panel>

      <Divider className="my-[var(--divider-margin)]" />

      {/* ========================================================================= */}
      {/* 1. REPORT VIEWER MODAL DIALOG                                              */}
      {/* ========================================================================= */}
      {viewingReport && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-canvas)]/80 backdrop-blur-sm p-[var(--space-4)] sm:p-[var(--space-6)]"
          onClick={() => setViewingReport(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="report-modal-title"
        >
          <div
            className="flex flex-col w-full max-w-4xl max-h-[90vh] rounded-[var(--radius-xl)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] shadow-[var(--shadow-xl)] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <PanelHeader
              title={viewingReport.title}
              subtitle={
                <div className="mt-1.5 flex flex-wrap items-center gap-[var(--space-2)] text-xs">
                  <span className="font-mono text-[var(--color-fg-muted)]">{viewingReport.id}</span>
                  <span className="text-[var(--color-fg-muted)]/20">•</span>
                  <span className="font-mono text-[var(--color-accent-fg)]">{viewingReport.incident_id}</span>
                  <span className="text-[var(--color-fg-muted)]/20">•</span>
                  <Badge tone="muted" className="text-[10px] uppercase font-mono">
                    {viewingReport.format}
                  </Badge>
                  <Badge tone="success" dot className="text-[10px]">
                    {viewingReport.status}
                  </Badge>
                  <span className="text-[var(--color-fg-muted)] text-[11px]">{formatDate(viewingReport.generated_at)}</span>
                </div>
              }
              divider={true}
              actions={
                <button
                  onClick={() => setViewingReport(null)}
                  className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)]"
                  aria-label="Close report viewer"
                >
                  <X className="h-5 w-5" />
                </button>
              }
            />

            {/* Modal Tabs Bar */}
            <div className="flex items-center justify-between border-b border-[var(--color-border-default)] px-[var(--space-6)] bg-[var(--color-canvas-subtle)]/50">
              <div className="flex items-center gap-[var(--space-6)]">
                {(["summary", "document", "json"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveViewTab(tab)}
                    className={`py-[var(--space-3)] text-xs font-semibold uppercase tracking-wider transition-colors border-b-2 ${
                      activeViewTab === tab
                        ? "border-[var(--color-accent-fg)] text-[var(--color-accent-fg)]"
                        : "border-transparent text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                    }`}
                  >
                    {tab === "summary" ? "Summary & Findings" : tab === "document" ? "Formatted Document" : "Raw JSON Data"}
                  </button>
                ))}
              </div>
              {activeViewTab === "json" && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopyJson}
                  className="gap-[var(--space-1)] text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                >
                  {copiedJson ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-[var(--color-success-fg)]" />
                      <span className="text-[var(--color-success-fg)]">Copied!</span>
                    </>
                  ) : (
                    <>
                      <FileText className="h-3.5 w-3.5" />
                      Copy JSON
                    </>
                  )}
                </Button>
              )}
            </div>

            {/* Modal Body */}
            <div className="flex-1 min-h-0 overflow-y-auto p-[var(--space-6)] overscroll-contain">
              <div className="space-y-[var(--space-6)]">
                {loadingViewData ? (
                  <div className="flex flex-col items-center justify-center py-[var(--space-16)] gap-[var(--space-3)]">
                    <div className="flex h-8 w-8 animate-spin text-[var(--color-accent-fg)]">
                      <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
                    </div>
                    <p className="text-sm text-[var(--color-fg-muted)]">Loading report details...</p>
                  </div>
                ) : activeViewTab === "summary" ? (
                  <>
                    {/* Incident Information */}
                    <Panel variant="inset" padding="md">
                      <PanelHeader
                        title="Incident Overview"
                        subtitle={
                          <Badge tone="primary" className="text-[10px] font-mono">
                            {viewingReportData?.system_name || "Unavailable"}
                          </Badge>
                        }
                      />
                      <PanelSection dividerBefore={false} className="text-sm text-[var(--color-fg-muted)]">
                        {viewingReportData?.description || "No description recorded for this incident."}
                      </PanelSection>
                      <PanelSection dividerBefore={true} className="grid grid-cols-2 sm:grid-cols-3 gap-[var(--space-3)] pt-[var(--space-2)] border-t border-[var(--color-border-default)] text-xs">
                        <div>
                          <span className="text-[var(--color-fg-muted)] block">Incident ID</span>
                          <span className="font-mono text-[var(--color-fg-default)]">{viewingReport.incident_id}</span>
                        </div>
                        <div>
                          <span className="text-[var(--color-fg-muted)] block">Evidence Items</span>
                          <span className="font-mono text-[var(--color-success-fg)]">
                            {viewingReportData?.evidence_summary
                              ? `${viewingReportData.evidence_summary.total_evidence_items ?? 0} recorded`
                              : "—"}
                          </span>
                        </div>
                        <div>
                          <span className="text-[var(--color-fg-muted)] block">Estimated Size</span>
                          <span className="font-mono text-[var(--color-fg-default)]">{formatBytes(viewingReport.size_bytes)}</span>
                        </div>
                      </PanelSection>
                    </Panel>

                    {/* Causal Hypotheses */}
                    <div className="space-y-[var(--space-3)]">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] flex items-center gap-[var(--space-2)]">
                        <Zap className="h-4 w-4 text-[var(--color-accent-fg)]" /> Root Cause Hypotheses
                      </h4>
                      <div className="space-y-[var(--space-2)]">
                        {(viewingReportData?.hypotheses || []).map((h: any, idx: number) => (
                          <Panel variant="inset" key={idx} padding="md">
                            <PanelSection dividerBefore={false} className="flex flex-col gap-[var(--space-2)]">
                              <div className="flex items-center justify-between">
                                <span className="font-mono font-semibold text-[var(--color-fg-default)] text-sm">
                                  {h.hypothesis_id}: {h.status}
                                </span>
                                <Badge
                                  tone={h.status === "CONFIRMED" ? "success" : "muted"}
                                  className="text-[10px]"
                                >
                                  {Math.round((h.confidence_posterior || h.confidence_prior || 0) * 100)}% Confidence
                                </Badge>
                              </div>
                              <p className="text-xs text-[var(--color-fg-muted)] leading-relaxed">{h.causal_claim}</p>
                              {h.supporting_artifact_ids?.length > 0 && (
                                <div className="text-[11px] text-[var(--color-fg-muted)] flex items-center gap-1.5 pt-1">
                                  <span className="text-[var(--color-fg-muted)]/70">Supporting Evidence:</span>
                                  {h.supporting_artifact_ids.map((art: string, i: number) => (
                                    <code key={i} className="px-1.5 py-0.5 rounded bg-[var(--color-canvas-subtle)]/50 font-mono text-[var(--color-accent-fg)] text-[10px]">
                                      {art}
                                    </code>
                                  ))}
                                </div>
                              )}
                            </PanelSection>
                          </Panel>
                        ))}
                      </div>
                    </div>

                    {/* Verification Summary — rendered from the server's own verification records */}
                    <Panel
                      variant="inset"
                      padding="md"
                      className={
                        verifiedReport
                          ? "border border-[var(--color-success-muted)] bg-[var(--color-success-muted)]/5"
                          : "border border-[var(--color-danger-muted)] bg-[var(--color-danger-muted)]/5"
                      }
                    >
                      <PanelSection dividerBefore={false} className="flex items-start gap-3">
                        <Shield
                          className={`h-5 w-5 mt-0.5 flex-shrink-0 ${verifiedReport ? "text-[var(--color-success-fg)]" : "text-[var(--color-danger-fg)]"}`}
                        />
                        <div>
                          <h4 className="text-sm font-semibold text-[var(--color-fg-default)]">
                            {verifiedReport ? "Verified Remediation Available" : "No Verified Remediation"}
                          </h4>
                          <p className="text-xs text-[var(--color-fg-muted)] mt-1 leading-relaxed">
                            {verifiedReport
                              ? `Verified patch ${selectedPatchId} passed ${gatesPassed} of ${INVARIANT_CHECKS.length} invariant gates in digital-twin verification.`
                              : "No patch candidate cleared all nine invariant gates; no verified remediation is available for this incident."}
                          </p>
                        </div>
                      </PanelSection>
                    </Panel>
                  </>
                ) : activeViewTab === "document" ? (
                  /* Formatted Document View */
                  <Panel variant="inset" padding="lg" className="space-y-[var(--space-6)] text-sm">
                    <div className="border-b border-[var(--color-border-default)] pb-[var(--space-4)]">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-[var(--color-accent-fg)] tracking-widest uppercase">Cauveris System Report</span>
                        <button
                          onClick={() => window.print()}
                          className="flex items-center gap-[var(--space-1)] text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] transition-colors"
                        >
                          <ExternalLink className="h-3.5 w-3.5" /> Print
                        </button>
                      </div>
                      <h3 className="text-lg font-bold text-[var(--color-fg-default)] mt-1">{viewingReport.title}</h3>
                      <p className="text-xs text-[var(--color-fg-muted)] font-mono mt-[var(--space-1)]">
                        Target: {viewingReportData?.system_name || "Unavailable"} • Generated: {formatDate(viewingReport.generated_at)}
                      </p>
                    </div>

                    <div className="space-y-[var(--space-2)]">
                      <h5 className="text-xs font-bold text-[var(--color-fg-muted)] uppercase">Executive Summary</h5>
                      <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
                        {viewingReportData?.description || "No description recorded for this incident."}
                      </p>
                    </div>

                    <div className="space-y-[var(--space-2)]">
                      <h5 className="text-xs font-bold text-[var(--color-fg-muted)] uppercase">Causal Evidence Analysis</h5>
                      <Panel variant="inset" padding="md" className="text-xs space-y-[var(--space-2)]">
                        <div className="flex justify-between">
                          <span className="text-[var(--color-fg-muted)]">Total Evidence Items:</span>
                          <span className="text-[var(--color-fg-default)] font-mono">{viewingReportData?.evidence_summary?.total_evidence_items ?? 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[var(--color-fg-muted)]">Required Evidence Items:</span>
                          <span className="text-[var(--color-fg-default)] font-mono">{viewingReportData?.evidence_summary?.required_evidence_items ?? 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[var(--color-fg-muted)]">Missing Evidence:</span>
                          <span className={missingEvidence.length ? "text-[var(--color-danger-fg)] font-mono" : "text-[var(--color-success-fg)] font-mono"}>
                            {missingEvidence.length ? missingEvidence.join(", ") : "None"}
                          </span>
                        </div>
                      </Panel>
                    </div>

                    <div className="space-y-[var(--space-2)]">
                      <h5 className="text-xs font-bold text-[var(--color-fg-muted)] uppercase">Verified Resolution</h5>
                      <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
                        {selectedPatchId ? (
                          <>
                            Deploy verified patch candidate{" "}
                            <code className="text-[var(--color-accent-fg)] font-mono">{selectedPatchId}</code>
                            {selectedPatch?.target_file ? ` (${selectedPatch.target_file})` : ""}.
                          </>
                        ) : (
                          "No verified remediation is available for this incident."
                        )}
                      </p>
                    </div>
                  </Panel>
                ) : (
                  /* Raw JSON View */
                  <Panel variant="inset" padding="lg">
                    <pre className="font-mono text-xs text-[var(--color-fg-muted)] overflow-x-auto leading-relaxed max-h-[50vh]">
                      {JSON.stringify(viewingReportData, null, 2)}
                    </pre>
                  </Panel>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <PanelFooter className="border-t border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/50">
              <div className="flex items-center justify-between w-full">
                <div className="text-xs text-[var(--color-fg-muted)] font-mono">
                  {viewingReport.id} • {viewingReport.format.toUpperCase()}
                </div>
                <div className="text-xs text-[var(--color-fg-subtle)]">
                  Press Esc or click outside to dismiss
                </div>
              </div>
            </PanelFooter>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. DELETE CONFIRMATION MODAL                                              */}
      {/* ========================================================================= */}
      {deletingReport && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-canvas)]/80 backdrop-blur-sm p-[var(--space-4)]"
          onClick={() => setDeletingReport(null)}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          aria-describedby="delete-dialog-desc"
        >
          <div
            className="flex flex-col w-full max-w-md rounded-[var(--radius-xl)] bg-[var(--color-canvas-inset)] border border-[var(--color-danger-muted)] shadow-[var(--shadow-xl)] p-[var(--space-6)] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            <Panel variant="inset" padding="none">
              <PanelSection dividerBefore={false} className="flex items-start gap-[var(--space-4)]">
                <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-danger-muted)]/15 text-[var(--color-danger-fg)] border border-[var(--color-danger-muted)]/25">
                  <AlertTriangle className="h-5 w-5" />
                </div>
                <div>
                  <h3 id="delete-dialog-title" className="text-lg font-bold text-[var(--color-fg-default)]">
                    Delete Report
                  </h3>
                  <p id="delete-dialog-desc" className="mt-1 text-sm text-[var(--color-fg-muted)]">
                    Are you sure you want to delete <strong className="text-[var(--color-fg-default)] font-medium">{deletingReport.title}</strong> ({deletingReport.id})? This action cannot be undone.
                  </p>
                </div>
              </PanelSection>

              <PanelFooter dividerBefore={true} className="flex items-center justify-end gap-[var(--space-3)]">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDeletingReport(null)}
                >
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={handleConfirmDelete}
                  className="gap-[var(--space-1)]"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete Report
                </Button>
              </PanelFooter>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}

export { ReportsPage as ReportPage };
export default ReportsPage;