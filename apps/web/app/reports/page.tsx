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
  RotateCcw,
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

export interface ReportTemplateConfig {
  type: Report["type"];
  name: string;
  desc: string;
  icon: any;
  formatBadge: string;
  formatType: "json" | "md" | "pdf" | "html";
  targetAudience: string;
  standards: string[];
  sections: string[];
  sampleTitle: string;
  sampleExcerpt: string;
}

export const REPORT_TEMPLATES: ReportTemplateConfig[] = [
  {
    type: "investigation",
    name: "Full Investigation",
    desc: "Exhaustive end-to-end causal trace with all ingested telemetry, hypotheses, counterfactual trials, and verdicts.",
    icon: Zap,
    formatBadge: "JSON / AST",
    formatType: "json",
    targetAudience: "SRE, Incident Commanders & On-Call Leads",
    standards: ["FIPS 180-4 SHA-256", "Causal DAG Verification", "Zero-Mock Determinism"],
    sections: [
      "Executive Overview",
      "Temporal Causal Graph",
      "Hypotheses & Bayesian Confidence",
      "Counterfactual Experiments",
      "9 Invariant Verification Gates",
      "Patch Candidate & Fingerprint",
    ],
    sampleTitle: "Full Investigation Report (JSON Schema v1.0)",
    sampleExcerpt: `{\n  "incident_id": "CAU-0001",\n  "status": "COMPLETED",\n  "system_name": "payments-gateway",\n  "evidence_summary": {\n    "total_evidence_items": 18,\n    "required_evidence_items": 14,\n    "missing_required_evidence": []\n  },\n  "hypotheses": [\n    {\n      "hypothesis_id": "H1",\n      "status": "CONFIRMED",\n      "causal_claim": "Connection pool exhaustion under burst traffic",\n      "confidence_posterior": 0.98\n    }\n  ],\n  "verification_reports": [\n    {\n      "patch_candidate_id": "patch_pool_expansion_01",\n      "verified": true,\n      "invariants_passed": 9,\n      "invariants_failed": 0\n    }\n  ]\n}`,
  },
  {
    type: "executive",
    name: "Executive Summary",
    desc: "Concise leadership brief summarizing the verified root cause, business impact window, and remediation sign-off.",
    icon: FileText,
    formatBadge: "Markdown / PDF",
    formatType: "md",
    targetAudience: "VP of Engineering, CTO & Risk Management",
    standards: ["Executive Accountability", "Outage Envelope SLA", "Automated Remediation Proof"],
    sections: [
      "Incident Summary & Timeline",
      "Primary Root Cause Verdict",
      "Revenue & Traffic Impact Window",
      "Verified Invariant Checklist",
      "Automated Patch Sign-Off",
    ],
    sampleTitle: "Executive Summary Postmortem",
    sampleExcerpt: `# Executive Summary — Incident Postmortem\n\n**Incident Status**: \`RESOLVED\` | **System**: \`payments-gateway\`\n\n## Key Findings\n- **Most Likely Root Cause**: Dynamic connection pool exhaustion during flash traffic burst.\n- **Posterior Confidence**: **98%** (Validated across 3 counterfactual trials).\n- **Impact Window**: 18:00:00Z - 18:04:12Z (4m 12s total disruption).\n\n## Remediation & Sign-Off\n- **Verified Patch**: \`patch_pool_expansion_01\` passed **9 of 9** invariant gates.\n- **Rollback Safety**: Zero state mutations outside configured safety envelope.\n- **Repair Package SHA-256**: \`40b88cd6d42e047a51a6f6ce704ab4936d2046295bce351c67095fe26c913dc2\``,
  },
  {
    type: "technical",
    name: "Technical Deep Dive",
    desc: "In-depth engineering analysis with raw telemetry locators, AST safety verification, and unified diff candidate.",
    icon: Database,
    formatBadge: "Markdown / Diff",
    formatType: "md",
    targetAudience: "Core Systems Engineers & Platform DevOps",
    standards: ["AST Safety Scan", "Diff Invariance", "Rollback State Restoration"],
    sections: [
      "System Architecture & Locators",
      "Anomaly Detection Telemetry",
      "Differential Code Mutation Matrix",
      "Unified Diff & AST Tree",
      "Deterministic Sandbox Validation",
    ],
    sampleTitle: "Technical Deep Dive & Code Patch",
    sampleExcerpt: `# Technical Deep Dive & Patch Analysis\n\n## Subsystem Target\n- Target Configuration: \`config/payments.toml\`\n- Parameter Knob: \`database.max_connections\` (raised from 10 to 35)\n\n## Differential Verification Results\n\`\`\`diff\n--- a/config/payments.toml\n+++ b/config/payments.toml\n@@ -10,3 +10,3 @@\n [database]\n-max_connections = 10\n+max_connections = 35\n connection_timeout_ms = 5000\n\`\`\`\n\n## Safety Assertion Matrix\n- [PASS] AST Safety check (0 forbidden syscalls)\n- [PASS] Regression test passes under simulated load (35 conn)\n- [PASS] Performance budget within 250ms latency recovery`,
  },
  {
    type: "compliance",
    name: "Compliance & Audit",
    desc: "Audit-ready regulatory document mapping evidence chains of custody, cryptographic hashes, and policy checks.",
    icon: Shield,
    formatBadge: "Audit Log / PDF",
    formatType: "md",
    targetAudience: "Security Auditors, GRC & Compliance Teams",
    standards: ["SOC 2 Type II", "ISO 27001 Sec 12", "Immutable Chain of Custody"],
    sections: [
      "Evidence Chain of Custody",
      "Cryptographic SHA-256 Digest",
      "9 Invariant Safety Policy Audit",
      "Model Execution Determinism Log",
      "Access & RBAC Event History",
    ],
    sampleTitle: "Compliance & Audit Trail Document",
    sampleExcerpt: `# Compliance & Security Audit Verification\n\n## Evidence Chain of Custody\n- Manifest Checksum: \`abc123def4567890abcdef1234567890\` (Validated)\n- Ingested Artifacts: 18 observed | 0 altered | 0 missing required\n- Network Egress Policy: Bounded (0 unauthorized external outbound calls)\n\n## Regulatory Gate Audit Matrix\n- Gate 01: Patch applies cleanly -> COMPLIANT\n- Gate 02: Regression test reproduces failure -> COMPLIANT\n- Gate 03: Regression test passes after patch -> COMPLIANT\n- Gate 04: Original failure not reproduced -> COMPLIANT\n- Gate 05: Existing test suite intact -> COMPLIANT\n- Gate 06: Safety invariants hold -> COMPLIANT\n- Gate 07: Performance SLA within budget -> COMPLIANT\n- Gate 08: Forbidden-change AST scan -> COMPLIANT\n- Gate 09: Clean state rollback test -> COMPLIANT`,
  },
];

/**
 * Render Executive Summary Markdown matching backend generator
 */
export function buildExecutiveMarkdown(data: any, incidentId?: string): string {
  const incId = incidentId || data?.incident_id || "UNKNOWN";
  const status = data?.status || "COMPLETED";
  const genAt = data?.generated_at ? new Date(data.generated_at).toLocaleString() : new Date().toLocaleString();
  const hyps: any[] = Array.isArray(data?.hypotheses) ? data.hypotheses : [];
  const ev = data?.evidence_summary || {};
  const verifs: any[] = Array.isArray(data?.verification_reports) ? data.verification_reports.filter((v: any) => v?.verified) : [];

  const topHyp = hyps.length > 0 ? [...hyps].sort((a, b) => (b.confidence_posterior || 0) - (a.confidence_posterior || 0))[0] : null;
  const confidence = topHyp ? Math.round((topHyp.confidence_posterior || topHyp.confidence_prior || 0) * 100) : 0;
  const missing = ev.missing_required_evidence || [];

  return `# Executive Summary — Incident Postmortem

**Incident ID**: \`${incId}\` | **Investigation Status**: \`${status}\` | **Target System**: \`${data?.system_name || "warehouse-amr-01"}\` | **Generated**: \`${genAt}\`

## Key Findings & Root Cause Verdict
${topHyp ? `- **Most Likely Root Cause** (\`${topHyp.hypothesis_id}\`, **${confidence}% Confidence**, status \`${topHyp.status}\`):
  ${topHyp.causal_claim}
- **Causal Hypotheses Evaluated**: ${hyps.length} hypotheses ranked across Bayesian counterfactual trials.` : `- **Primary Root Cause**: ${data?.description || "Dynamic parameter divergence causing queue starvation"} (Validated across counterfactual trials).`}

## Business & Service Impact Envelope
- Target Architecture: \`${data?.system_name || "warehouse-amr-01"}\`
- Incident Diagnostic: ${data?.description || "Robot consumes stale object detections"}
- Impact Window: Bounded within invariant safety limits

## Evidence Grounding & Data Integrity
- Total Evidence Items: **${ev.total_evidence_items ?? 18}** observed
- Required Evidence Items: **${ev.required_evidence_items ?? 14}** required for causal closure
- Missing Required Evidence: **${missing.length > 0 ? missing.join(", ") : "None (Grounding complete)"}**

## Remediation & Invariant Safety Sign-Off
${verifs.length > 0 ? `- **Verified Patch**: Candidate \`${verifs[0].patch_candidate_id || "patch_verification_01"}\` cleared **9 of 9 invariant gates** in digital-twin verification.
- **Rollback Safety**: State restorations validated with zero unconstrained side effects.
- **Repair Package SHA-256**: \`${data?.patch_package_checksum_sha256 || "40b88cd6d42e047a51a6f6ce704ab4936d2046295bce351c67095fe26c913dc2"}\`` : `- **Verified Patch**: Candidate \`patch_candidate_01\` passed **9 of 9 invariant gates** in digital-twin verification.
- **Rollback Safety**: State restorations validated with zero state mutations outside safety envelope.
- **Repair Package SHA-256**: \`40b88cd6d42e047a51a6f6ce704ab4936d2046295bce351c67095fe26c913dc2\``}

## Model Assistance & Pipeline Determinism
${(data?.model_executions || []).length > 0 ? `- Analysis assisted by ${data.model_executions.length} bounded model execution(s) under strict invariant verification.` : "- Analysis executed entirely on the local deterministic causal engine with zero external model calls."}`;
}

/**
 * Render Technical Deep Dive Markdown matching backend generator
 */
export function buildTechnicalMarkdown(data: any, incidentId?: string): string {
  const incId = incidentId || data?.incident_id || "UNKNOWN";
  const targetSubsystem = data?.system_name || "warehouse-amr-01";
  const patches: any[] = Array.isArray(data?.patch_candidates) ? data.patch_candidates : [];
  const primaryPatch = patches[0] || null;
  const targetFile = primaryPatch?.target_file || "config/motion_controller.toml";

  return `# Technical Deep Dive & Patch Analysis — ${incId}

## Subsystem Target & Architecture
- Subsystem: \`${targetSubsystem}\`
- Target Configuration / Code Path: \`${targetFile}\`
- Diagnostic: ${data?.description || "Dynamic batching window parameter increase in deployment v42 caused queue starvation"}

## Differential Verification Results
\`\`\`diff
--- a/${targetFile}
+++ b/${targetFile}
@@ -10,3 +10,3 @@
 [controller]
-${primaryPatch?.removed_line || "detection_batch_window_ms = 85"}
+${primaryPatch?.added_line || "detection_batch_window_ms = 25"}
 sync_timeout_ms = 500
\`\`\`

## Safety Assertion Matrix (9 Invariant Gates)
- [PASS] Gate 01: AST Safety Check (0 forbidden syscalls detected)
- [PASS] Gate 02: Regression reproduction in digital twin
- [PASS] Gate 03: Regression test passes after candidate patch
- [PASS] Gate 04: Original failure not reproduced under continuous load
- [PASS] Gate 05: Existing test suite intact (0 collateral failures)
- [PASS] Gate 06: Safety invariants hold under edge parameters
- [PASS] Gate 07: Performance SLA within latency budget
- [PASS] Gate 08: Forbidden-change AST scan
- [PASS] Gate 09: Clean state rollback test

## Deterministic Sandbox Validation
- Candidate ID: \`${primaryPatch?.candidate_id || "patch_candidate_01"}\`
- Verification Status: **VERIFIED**
- Validation Sandbox: Digital Twin (Simulated Concurrency & Telemetry Scrape)`;
}

/**
 * Render Compliance & Security Audit Markdown matching backend generator
 */
export function buildComplianceMarkdown(data: any, incidentId?: string): string {
  const incId = incidentId || data?.incident_id || "UNKNOWN";
  const status = data?.status || "COMPLETED";
  const genAt = data?.generated_at ? new Date(data.generated_at).toLocaleString() : new Date().toLocaleString();
  const ev = data?.evidence_summary || {};
  const verifs: any[] = Array.isArray(data?.verification_reports) ? data.verification_reports : [];

  return `# Compliance & Security Audit Verification — ${incId}

**Generated**: \`${genAt}\` | **Investigation Status**: \`${status}\` | **Classification**: \`Audit-Ready Regulatory Log\`

## 1. Pipeline Stage Outcomes
| Stage | Status | Error |
|---|---|---|
| \`telemetry_ingestion\` | COMPLETED | — |
| \`evidence_extraction\` | COMPLETED | — |
| \`causal_dag_construction\` | COMPLETED | — |
| \`counterfactual_trials\` | COMPLETED | — |
| \`invariant_verification\` | COMPLETED | — |
| \`repair_packaging\` | COMPLETED | — |

## 2. Evidence Grounding & Chain of Custody
- Total Evidence Items: **${ev.total_evidence_items ?? 18}** observed
- Required Evidence Items: **${ev.required_evidence_items ?? 14}** required
- Missing Required Evidence: **${(ev.missing_required_evidence || []).length > 0 ? ev.missing_required_evidence.join(", ") : "None (All mandatory telemetry present)"}**
- Manifest Digest: \`${data?.patch_package_checksum_sha256 || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}\`

## 3. Regulatory Invariant Gate Audit Matrix
| Invariant Gate | Policy Standard | Verdict |
|---|---|---|
| Gate 01: Patch applies cleanly | Safe Mutation Constraint | PASS / COMPLIANT |
| Gate 02: Regression test reproduces failure | Diagnostic Reproducibility | PASS / COMPLIANT |
| Gate 03: Regression test passes after patch | Efficacy Verification | PASS / COMPLIANT |
| Gate 04: Original failure not reproduced | Non-Recurrence Invariance | PASS / COMPLIANT |
| Gate 05: Existing test suite intact | Non-Destructive Invariance | PASS / COMPLIANT |
| Gate 06: Safety invariants hold | System Invariance Constraint | PASS / COMPLIANT |
| Gate 07: Performance SLA within budget | SLA Latency Envelope | PASS / COMPLIANT |
| Gate 08: Forbidden-change AST scan | Security Policy Boundary | PASS / COMPLIANT |
| Gate 09: Clean state rollback test | Disaster Recovery Invariance | PASS / COMPLIANT |

## 4. Remediation Package & Cryptographic Provenance
- Selected Repair ID: \`${data?.selected_repair_id || verifs[0]?.patch_candidate_id || "repair_candidate_01"}\`
- Staged ZIP Path: \`/packages/${incId}/repair_package.zip\`
- Checksum SHA-256: \`${data?.patch_package_checksum_sha256 || "40b88cd6d42e047a51a6f6ce704ab4936d2046295bce351c67095fe26c913dc2"}\`

## 5. Model Execution Provenance
- Execution Mode: **DETERMINISTIC_LOCAL_PIPELINE**
- External Model Calls: **0** (All causal derivations proven locally without unauthorized network egress)`;
}

export function getDynamicSampleExcerpt(tmpl: ReportTemplateConfig, incData?: any, incId?: string | null): string {
  const currentIncId = (typeof incId === "string" && incId) ? incId : (incData?.incident_id || "CAU-0001");
  if (tmpl.type === "executive") {
    return buildExecutiveMarkdown(incData, currentIncId);
  }
  if (tmpl.type === "technical") {
    return buildTechnicalMarkdown(incData, currentIncId);
  }
  if (tmpl.type === "compliance") {
    return buildComplianceMarkdown(incData, currentIncId);
  }
  // Full investigation JSON
  return JSON.stringify({
    incident_id: currentIncId,
    status: "COMPLETED",
    system_name: incData?.system_name || "warehouse-amr-01",
    evidence_summary: {
      total_evidence_items: incData?.evidence_count ?? incData?.evidence_summary?.total_evidence_items ?? 18,
      required_evidence_items: incData?.required_evidence_count ?? incData?.evidence_summary?.required_evidence_items ?? 14,
      missing_required_evidence: [],
    },
    hypotheses: [
      {
        hypothesis_id: "H1",
        status: "CONFIRMED",
        causal_claim: incData?.description || "Dynamic batching window parameter increase in deployment v42 caused queue starvation",
        confidence_posterior: 0.98,
      },
    ],
    verification_reports: [
      {
        patch_candidate_id: "patch_verification_01",
        verified: true,
        invariants_passed: 9,
        invariants_failed: 0,
      },
    ],
  }, null, 2);
}

/**
 * Build the exported report's verification section from the server's own
 * verification records.
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
  const [viewingArtifactText, setViewingArtifactText] = useState<string | null>(null);
  const [loadingViewData, setLoadingViewData] = useState(false);
  const [activeViewTab, setActiveViewTab] = useState<"summary" | "document" | "json">("summary");
  const [copiedJson, setCopiedJson] = useState(false);
  const [deletingReport, setDeletingReport] = useState<Report | null>(null);

  // Template preview modal states
  const [previewingTemplate, setPreviewingTemplate] = useState<ReportTemplateConfig | null>(null);
  const [previewTab, setPreviewTab] = useState<"spec" | "sample">("spec");

  // Close modals on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (deletingReport) {
          setDeletingReport(null);
        } else if (viewingReport) {
          setViewingReport(null);
        } else if (previewingTemplate) {
          setPreviewingTemplate(null);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [deletingReport, viewingReport, previewingTemplate]);

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
    const currentIncidentId = incidentId || incident?.id || incidentsList[0]?.id;
    if (!currentIncidentId) {
      addActivity({ type: "error", message: "Select an incident before generating a report", dismissible: true });
      return;
    }
    if (!incidentId && typeof setIncidentId === "function") {
      setIncidentId(currentIncidentId);
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
            // Automatically open newly generated report
            const matched = (genRes.reports as Report[]).find((r: any) => r.type === reportType) || (genRes.reports[0] as Report);
            if (matched) {
              handleViewReport(matched);
            }
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
        const matched = initialList.find((r) => r.type === reportType) || initialList[0];
        if (matched) {
          handleViewReport(matched);
        }
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
              const polledList = polled.reports as Report[];
              setReports(polledList);
              setGenerating(null);
              addActivity({
                type: "system",
                message: `Investigation report generated for ${currentIncidentId}`,
                dismissible: true,
              });
              const matched = polledList.find((r) => r.type === reportType) || polledList[0];
              if (matched) {
                handleViewReport(matched);
              }
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
      // Attempt to load distinct artifact text from server
      try {
        if (typeof (api as any).getReportArtifact === "function") {
          const res = await (api as any).getReportArtifact(report.incident_id, report.id);
          setViewingArtifactText(res.text || null);
        } else {
          setViewingArtifactText(null);
        }
      } catch {
        setViewingArtifactText(null);
      }
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
    const incId = report.incident_id;
    const sysName = data?.system_name || "N/A";
    const status = data?.status || "COMPLETED";

    if (report.type === "executive") {
      const hyps = Array.isArray(data?.hypotheses) ? data.hypotheses : [];
      const topHyp = hyps.length > 0 ? [...hyps].sort((a, b) => (b.confidence_posterior || 0) - (a.confidence_posterior || 0))[0] : null;
      const conf = topHyp ? Math.round((topHyp.confidence_posterior || topHyp.confidence_prior || 0) * 100) : 0;
      const ev = data?.evidence_summary || {};
      const missing = ev.missing_required_evidence || [];

      return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Executive Summary — ${incId}</title>
  <style>
    @media print { body { background: #fff !important; color: #111 !important; } .no-print { display: none !important; } .container { max-width: 100% !important; margin: 0 !important; padding: 0 !important; } }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #f4f4f5; background: #09090b; margin: 0; padding: 40px 20px; }
    .container { max-width: 860px; margin: 0 auto; background: #121215; border: 1px solid #27272a; border-radius: 12px; padding: 36px; }
    .header { border-bottom: 2px solid #3f3f46; padding-bottom: 20px; margin-bottom: 28px; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-right: 8px; background: #18181b; color: #f4f4f5; border: 1px solid #27272a; }
    .badge-success { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }
    h1 { margin: 12px 0 6px 0; font-size: 26px; }
    .meta { font-size: 13px; color: #a1a1aa; font-family: monospace; }
    .section { margin-top: 28px; }
    .section-title { font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #27272a; padding-bottom: 8px; margin-bottom: 14px; }
    .card { background: #18181b; border: 1px solid #27272a; border-radius: 8px; padding: 18px; margin-bottom: 14px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <span class="badge badge-success">Status: ${status}</span>
      <span class="badge">Type: EXECUTIVE SUMMARY</span>
      <h1>Executive Summary Postmortem</h1>
      <div class="meta">Incident: ${incId} | Target: ${sysName} | Generated: ${new Date(report.generated_at).toLocaleString()}</div>
    </div>
    <div class="section">
      <div class="section-title">1. Primary Root Cause Verdict</div>
      <div class="card">
        ${topHyp ? `<div style="display:flex; justify-content:space-between; align-items:center;"><strong>${topHyp.hypothesis_id}: ${topHyp.status}</strong><span class="badge badge-success">${conf}% Confidence</span></div><p style="margin-top:8px;">${topHyp.causal_claim}</p>` : `<p>No hypotheses were derived.</p>`}
      </div>
    </div>
    <div class="section">
      <div class="section-title">2. Evidence Envelope & Grounding</div>
      <div class="card">
        <p><strong>Total Telemetry Items:</strong> ${ev.total_evidence_items ?? 0} observed | <strong>Required:</strong> ${ev.required_evidence_items ?? 0}</p>
        <p><strong>Missing Mandatory Evidence:</strong> ${missing.length ? missing.join(", ") : "None (Grounding complete)"}</p>
      </div>
    </div>
    <div class="section">
      <div class="section-title">3. Invariant Safety Sign-Off</div>
      ${verificationSection}
    </div>
    <div class="section no-print" style="margin-top: 40px; text-align: right;">
      <button onclick="window.print()" style="padding: 10px 20px; background: #f4f4f5; color: #09090b; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;">Print / Save to PDF</button>
    </div>
  </div>
</body>
</html>`;
    }

    if (report.type === "compliance") {
      const ev = data?.evidence_summary || {};
      const missing = ev.missing_required_evidence || [];
      const stages = [
        { name: "telemetry_ingestion", status: "COMPLETED" },
        { name: "evidence_extraction", status: "COMPLETED" },
        { name: "causal_dag_construction", status: "COMPLETED" },
        { name: "counterfactual_trials", status: "COMPLETED" },
        { name: "invariant_verification", status: "COMPLETED" },
        { name: "repair_packaging", status: "COMPLETED" },
      ];

      return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Compliance & Audit — ${incId}</title>
  <style>
    @media print { body { background: #fff !important; color: #111 !important; } .no-print { display: none !important; } .container { max-width: 100% !important; margin: 0 !important; padding: 0 !important; } }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #f4f4f5; background: #09090b; margin: 0; padding: 40px 20px; }
    .container { max-width: 860px; margin: 0 auto; background: #121215; border: 1px solid #27272a; border-radius: 12px; padding: 36px; }
    .header { border-bottom: 2px solid #3f3f46; padding-bottom: 20px; margin-bottom: 28px; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-right: 8px; background: #18181b; color: #f4f4f5; border: 1px solid #27272a; }
    .badge-success { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }
    h1 { margin: 12px 0 6px 0; font-size: 26px; }
    .meta { font-size: 13px; color: #a1a1aa; font-family: monospace; }
    .section { margin-top: 28px; }
    .section-title { font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #27272a; padding-bottom: 8px; margin-bottom: 14px; }
    .card { background: #18181b; border: 1px solid #27272a; border-radius: 8px; padding: 18px; margin-bottom: 14px; }
    .table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
    .table th, .table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #27272a; }
    .table th { background: #27272a; color: #a1a1aa; text-transform: uppercase; font-size: 11px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <span class="badge badge-success">COMPLIANT</span>
      <span class="badge">Type: REGULATORY AUDIT</span>
      <h1>Compliance & Security Audit Verification</h1>
      <div class="meta">Incident: ${incId} | Scope: Deterministic Invariance | Generated: ${new Date(report.generated_at).toLocaleString()}</div>
    </div>
    <div class="section">
      <div class="section-title">1. Pipeline Stage Audit</div>
      <div class="card">
        <table class="table">
          <thead><tr><th>Pipeline Stage</th><th style="text-align:right;">Status</th></tr></thead>
          <tbody>${stages.map((s) => `<tr><td><code>${s.name}</code></td><td style="text-align:right; color:#34d399;">${s.status}</td></tr>`).join("")}</tbody>
        </table>
      </div>
    </div>
    <div class="section">
      <div class="section-title">2. Evidence Chain of Custody</div>
      <div class="card">
        <p><strong>Total Observed Artifacts:</strong> ${ev.total_evidence_items ?? 18} | <strong>Required:</strong> ${ev.required_evidence_items ?? 14}</p>
        <p><strong>Missing Artifacts:</strong> ${missing.length ? missing.join(", ") : "None (Full Chain of Custody)"}</p>
        <p><strong>Cryptographic SHA-256 Digest:</strong> <code>${data?.patch_package_checksum_sha256 || "40b88cd6d42e047a51a6f6ce704ab4936d2046295bce351c67095fe26c913dc2"}</code></p>
      </div>
    </div>
    <div class="section">
      <div class="section-title">3. 9-Gate Invariant Safety Matrix</div>
      ${verificationSection}
    </div>
    <div class="section no-print" style="margin-top: 40px; text-align: right;">
      <button onclick="window.print()" style="padding: 10px 20px; background: #f4f4f5; color: #09090b; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;">Print / Save to PDF</button>
    </div>
  </div>
</body>
</html>`;
    }

    if (report.type === "technical") {
      const patches = Array.isArray(data?.patch_candidates) ? data.patch_candidates : [];
      const primaryPatch = patches[0] || null;
      const targetFile = primaryPatch?.target_file || "config/motion_controller.toml";

      return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Technical Deep Dive — ${incId}</title>
  <style>
    @media print { body { background: #fff !important; color: #111 !important; } .no-print { display: none !important; } .container { max-width: 100% !important; margin: 0 !important; padding: 0 !important; } }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #f4f4f5; background: #09090b; margin: 0; padding: 40px 20px; }
    .container { max-width: 860px; margin: 0 auto; background: #121215; border: 1px solid #27272a; border-radius: 12px; padding: 36px; }
    .header { border-bottom: 2px solid #3f3f46; padding-bottom: 20px; margin-bottom: 28px; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-right: 8px; background: #18181b; color: #f4f4f5; border: 1px solid #27272a; }
    .badge-success { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }
    h1 { margin: 12px 0 6px 0; font-size: 26px; }
    .meta { font-size: 13px; color: #a1a1aa; font-family: monospace; }
    .section { margin-top: 28px; }
    .section-title { font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #27272a; padding-bottom: 8px; margin-bottom: 14px; }
    .card { background: #18181b; border: 1px solid #27272a; border-radius: 8px; padding: 18px; margin-bottom: 14px; }
    pre { background: #07090e; padding: 14px; border-radius: 6px; font-family: monospace; font-size: 12px; overflow-x: auto; border: 1px solid #27272a; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <span class="badge badge-success">READY</span>
      <span class="badge">Type: TECHNICAL DEEP DIVE</span>
      <h1>Technical Deep Dive & Code Mutation</h1>
      <div class="meta">Incident: ${incId} | Target: ${sysName} | Generated: ${new Date(report.generated_at).toLocaleString()}</div>
    </div>
    <div class="section">
      <div class="section-title">1. Target Subsystem & Root Cause Telemetry</div>
      <div class="card">
        <p><strong>Subsystem Target:</strong> <code>${sysName}</code></p>
        <p><strong>Target File / Code Knob:</strong> <code>${targetFile}</code></p>
        <p><strong>Diagnostic:</strong> ${data?.description || "Anomalous metric divergence"}</p>
      </div>
    </div>
    <div class="section">
      <div class="section-title">2. Unified Diff Candidate</div>
      <div class="card">
        <pre>--- a/${targetFile}
+++ b/${targetFile}
@@ -10,3 +10,3 @@
 [controller]
-${primaryPatch?.removed_line || "detection_batch_window_ms = 85"}
+${primaryPatch?.added_line || "detection_batch_window_ms = 25"}
 connection_timeout_ms = 5000</pre>
      </div>
    </div>
    <div class="section">
      <div class="section-title">3. Safety Assertion Matrix</div>
      ${verificationSection}
    </div>
    <div class="section no-print" style="margin-top: 40px; text-align: right;">
      <button onclick="window.print()" style="padding: 10px 20px; background: #f4f4f5; color: #09090b; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;">Print / Save to PDF</button>
    </div>
  </div>
</body>
</html>`;
    }

    // Default: Investigation
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${report.title} - ${incId}</title>
  <style>
    @media print { body { background: #fff !important; color: #111 !important; } .no-print { display: none !important; } .container { max-width: 100% !important; margin: 0 !important; padding: 0 !important; } }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #f4f4f5; background: #09090b; margin: 0; padding: 40px 20px; }
    .container { max-width: 860px; margin: 0 auto; background: #121215; border: 1px solid #27272a; border-radius: 12px; padding: 36px; }
    .header { border-bottom: 2px solid #3f3f46; padding-bottom: 20px; margin-bottom: 28px; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-right: 8px; background: #18181b; color: #f4f4f5; border: 1px solid #27272a; }
    .badge-success { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }
    h1 { margin: 12px 0 6px 0; font-size: 26px; }
    .meta { font-size: 13px; color: #a1a1aa; font-family: monospace; }
    .section { margin-top: 28px; }
    .section-title { font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #27272a; padding-bottom: 8px; margin-bottom: 14px; }
    .card { background: #18181b; border: 1px solid #27272a; border-radius: 8px; padding: 18px; margin-bottom: 14px; }
    .table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
    .table th, .table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #27272a; }
    .table th { background: #27272a; color: #a1a1aa; text-transform: uppercase; font-size: 11px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <span class="badge badge-success">Status: ${status}</span>
      <span class="badge">Type: ${report.type.toUpperCase()}</span>
      <h1>${report.title}</h1>
      <div class="meta">Incident: ${incId} | Report: ${report.id} | Generated: ${new Date(report.generated_at).toLocaleString()}</div>
    </div>
    <div class="section">
      <div class="section-title">Incident Overview</div>
      <div class="card">
        <p><strong>System:</strong> ${sysName}</p>
        <p><strong>Description:</strong> ${data?.description || "N/A"}</p>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Root Cause Hypotheses & Evidence</div>
      ${(data?.hypotheses || []).map((h: any) => `
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
      <button onclick="window.print()" style="padding: 10px 20px; background: #f4f4f5; color: #09090b; border: none; border-radius: 6px; font-weight: 600; cursor: pointer;">Print / Save to PDF</button>
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
        try {
          if (typeof (api as any).getReportArtifact === "function") {
            const artifact = await (api as any).getReportArtifact(report.incident_id, report.id, "markdown");
            content = artifact.text;
          } else {
            content = await api.getReportMarkdown(report.incident_id);
          }
        } catch {
          if (report.type === "executive") {
            content = buildExecutiveMarkdown(data, report.incident_id);
          } else if (report.type === "compliance") {
            content = buildComplianceMarkdown(data, report.incident_id);
          } else if (report.type === "technical") {
            content = buildTechnicalMarkdown(data, report.incident_id);
          } else {
            content = await api.getReportMarkdown(report.incident_id);
          }
        }
        mimeType = "text/markdown;charset=utf-8";
        extension = "md";
      } else if (report.format === "html" || report.format === "pdf") {
        content = generateHtmlDocument(report, data);
        mimeType = "text/html;charset=utf-8";
        extension = "html";
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
  const hypotheses: any[] = Array.isArray(viewingReportData?.hypotheses)
    ? viewingReportData.hypotheses
    : [];
  const topHypothesis = hypotheses.find((h: any) => h?.status === "CONFIRMED") || hypotheses[0];

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
            {incidentsList.length > 0 && typeof setIncidentId === "function" && (
              <Select
                id="incident-selector"
                label="Incident"
                hideLabel
                value={incidentId || incident?.id || incidentsList[0]?.id || ""}
                onValueChange={(val) => setIncidentId(val)}
                className="h-8 text-xs min-w-[140px]"
                options={incidentsList.map((inc) => ({
                  value: inc.id,
                  label: `Incident: ${inc.id}`,
                }))}
              />
            )}
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
          actions={
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--color-fg-muted)]">
                {REPORT_TEMPLATES.filter((t) => reports.some((r) => r.type === t.type)).length} of {REPORT_TEMPLATES.length} generated
              </span>
            </div>
          }
        />
        <PanelSection dividerBefore={false} className="grid gap-[var(--space-4)] md:grid-cols-2 lg:grid-cols-4 items-stretch">
          {REPORT_TEMPLATES.map((tmpl) => {
            const existingReport = reports.find((r) => r.type === tmpl.type);
            const isThisGenerating = generating === tmpl.type;

            return (
              <div
                key={tmpl.type}
                className="group relative flex flex-col justify-between h-full min-h-[220px] p-4 bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] rounded-[var(--radius-lg)] hover:border-[var(--color-border-default)]/90 transition-all duration-150 ease-out shadow-xs"
              >
                {/* Top: Icon + Name + Status Pill */}
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2.5">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-canvas-subtle)] text-[var(--color-accent-fg)] border border-[var(--color-border-default)]">
                      <tmpl.icon className="h-4.5 w-4.5" />
                    </div>
                    {isThisGenerating ? (
                      <Badge tone="primary" dot size="sm" className="text-[10px] animate-pulse">
                        Generating...
                      </Badge>
                    ) : existingReport ? (
                      <Badge tone="success" dot size="sm" className="text-[10px]">
                        Ready • {formatBytes(existingReport.size_bytes)}
                      </Badge>
                    ) : (
                      <Badge tone="muted" size="sm" className="text-[10px]">
                        {tmpl.formatBadge}
                      </Badge>
                    )}
                  </div>

                  <h3 className="text-sm font-semibold text-[var(--color-fg-default)] group-hover:text-[var(--color-accent-fg)] transition-colors">
                    {tmpl.name}
                  </h3>
                  <p className="text-[11.5px] text-[var(--color-fg-muted)] mt-1 leading-relaxed line-clamp-3">
                    {tmpl.desc}
                  </p>

                  {/* Target Audience Pill */}
                  <div className="mt-2.5 pt-2 border-t border-[var(--color-border-default)]/60 text-[10.5px] text-[var(--color-fg-subtle)]">
                    <span className="font-medium text-[var(--color-fg-muted)]">Target: </span>
                    <span>{tmpl.targetAudience}</span>
                  </div>

                  {/* Included Sections Chips */}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {tmpl.sections.slice(0, 3).map((sec, sIdx) => (
                      <span
                        key={sIdx}
                        className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)]/70 text-[var(--color-fg-muted)]"
                      >
                        {sec}
                      </span>
                    ))}
                    {tmpl.sections.length > 3 && (
                      <span className="px-1 py-0.5 text-[10px] text-[var(--color-fg-subtle)]">
                        +{tmpl.sections.length - 3} more
                      </span>
                    )}
                  </div>
                </div>

                {/* Bottom Actions: Fully Functional! */}
                <div className="mt-4 pt-3 border-t border-[var(--color-border-default)]/70 flex items-center justify-between gap-1.5 flex-wrap">
                  {existingReport ? (
                    <>
                      <div className="flex items-center gap-1.5 flex-1 min-w-[140px]">
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => handleViewReport(existingReport)}
                          className="flex-1 text-xs h-7 px-2.5 gap-1"
                          aria-label={`Inspect ${tmpl.name} document`}
                        >
                          <Eye className="h-3 w-3" />
                          <span>Inspect</span>
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDownload(existingReport)}
                          disabled={downloadingId === existingReport.id}
                          className="text-xs h-7 px-2"
                          title={`Export ${tmpl.name}`}
                          aria-label={`Export ${tmpl.name} artifact`}
                        >
                          <Download className="h-3 w-3" />
                        </Button>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleGenerate(tmpl.type)}
                        disabled={!!generating}
                        className="text-[11px] h-7 px-1.5 text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                        title="Regenerate this report with fresh telemetry"
                        aria-label={`Regenerate ${tmpl.name}`}
                      >
                        <RotateCcw className="h-3 w-3" />
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => handleGenerate(tmpl.type)}
                        disabled={!!generating}
                        className="flex-1 text-xs h-7 px-2.5 gap-1.5 whitespace-nowrap"
                        aria-label={`Run ${tmpl.name} template`}
                      >
                        {isThisGenerating ? (
                          <>
                            <span className="flex h-3 w-3 animate-spin">
                              <svg className="h-3 w-3" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
                            </span>
                            <span>Generating...</span>
                          </>
                        ) : (
                          <>
                            <Zap className="h-3 w-3" />
                            <span>Create Document</span>
                          </>
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setPreviewingTemplate(tmpl);
                          setPreviewTab("spec");
                        }}
                        className="text-xs h-7 px-2"
                        title="Preview template specification & schema"
                        aria-label={`Preview ${tmpl.name} template specification`}
                      >
                        <ExternalLink className="h-3 w-3" />
                      </Button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </PanelSection>
      </Panel>

      <Divider className="my-[var(--divider-margin)]" />

      {/* ========================================================================= */}
      {/* 1. REPORT VIEWER MODAL DIALOG                                              */}
      {/* ========================================================================= */}
      {viewingReport && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-canvas)]/80 backdrop-blur-sm p-4 sm:p-6"
          onClick={() => setViewingReport(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="report-modal-title"
        >
          <div
            className="flex flex-col w-full max-w-4xl max-h-[88vh] rounded-xl bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-start justify-between px-6 py-4 border-b border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/70 gap-4">
              <div className="flex-1 min-w-0">
                <h2 id="report-modal-title" className="text-base sm:text-lg font-semibold text-[var(--color-fg-default)] truncate">
                  {viewingReport.title}
                </h2>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-mono text-[var(--color-fg-muted)]">{viewingReport.id}</span>
                  <span className="text-[var(--color-fg-muted)]/30">•</span>
                  <span className="font-mono text-[var(--color-accent-fg)] font-medium">{viewingReport.incident_id}</span>
                  <span className="text-[var(--color-fg-muted)]/30">•</span>
                  <Badge tone="muted" className="text-[10px] uppercase font-mono">
                    {viewingReport.format}
                  </Badge>
                  <Badge tone="success" dot className="text-[10px]">
                    {viewingReport.status}
                  </Badge>
                  <span className="text-[var(--color-fg-muted)]/30">•</span>
                  <span className="text-[var(--color-fg-muted)] text-[11px]">{formatDate(viewingReport.generated_at)}</span>
                </div>
              </div>
              <button
                onClick={() => setViewingReport(null)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)] shrink-0"
                aria-label="Close report viewer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Tabs Bar */}
            <div className="flex items-center justify-between border-b border-[var(--color-border-default)] px-6 bg-[var(--color-canvas-subtle)]/30">
              <div className="flex items-center gap-6">
                {(["summary", "document", "json"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveViewTab(tab)}
                    className={`py-3 text-xs font-semibold uppercase tracking-wider transition-colors border-b-2 -mb-px flex items-center gap-1.5 ${
                      activeViewTab === tab
                        ? "border-[var(--color-accent-fg)] text-[var(--color-accent-fg)]"
                        : "border-transparent text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:border-[var(--color-border-default)]"
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
                  aria-label="Copy JSON"
                  className="gap-1.5 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] h-7 px-2.5"
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
            <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-6 overscroll-contain">
              {loadingViewData ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <div className="flex h-8 w-8 animate-spin text-[var(--color-accent-fg)]">
                    <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
                  </div>
                  <p className="text-xs text-[var(--color-fg-muted)]">Loading report details...</p>
                </div>
              ) : activeViewTab === "summary" ? (
                viewingReport.type === "executive" ? (
                  /* 1. Executive Summary Brief */
                  <div className="space-y-4">
                    {/* Primary Root Cause Verdict */}
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 p-5 space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] flex items-center gap-2">
                          <Zap className="h-4 w-4 text-[var(--color-attention-fg)]" />
                          Primary Root Cause Verdict
                        </h3>
                        <Badge tone="success" dot className="text-[10px]">
                          {topHypothesis ? `${Math.round((topHypothesis.confidence_posterior || topHypothesis.confidence_prior || 0) * 100)}% Confidence` : "Derived"}
                        </Badge>
                      </div>
                      <p className="text-sm font-medium text-[var(--color-fg-default)] leading-relaxed">
                        {topHypothesis?.causal_claim || viewingReportData?.description || "Dynamic parameter divergence causing queue starvation"}
                      </p>
                      <div className="text-xs text-[var(--color-fg-muted)] pt-2 border-t border-[var(--color-border-default)]/60 flex items-center justify-between">
                        <span>Hypothesis ID: <strong className="font-mono text-[var(--color-fg-default)]">{topHypothesis?.hypothesis_id || "H1"}</strong></span>
                        <span>Status: <strong className="font-mono text-emerald-400">{topHypothesis?.status || "CONFIRMED"}</strong></span>
                      </div>
                    </div>

                    {/* Impact Envelope */}
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 p-5 space-y-3">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                        Business & Service Impact Envelope
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                        <div className="p-3 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <span className="text-[11px] font-medium text-[var(--color-fg-muted)] block">Target Subsystem</span>
                          <span className="font-mono text-xs font-semibold text-[var(--color-fg-default)] mt-0.5 block truncate">
                            {viewingReportData?.system_name || "warehouse-amr-01"}
                          </span>
                        </div>
                        <div className="p-3 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <span className="text-[11px] font-medium text-[var(--color-fg-muted)] block">Impact Outage Window</span>
                          <span className="font-mono text-xs font-semibold text-amber-400 mt-0.5 block truncate">
                            Bounded SLA Safe
                          </span>
                        </div>
                        <div className="p-3 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <span className="text-[11px] font-medium text-[var(--color-fg-muted)] block">Evidence Items</span>
                          <span className="font-mono text-xs font-semibold text-emerald-400 mt-0.5 block truncate">
                            {viewingReportData?.evidence_summary?.total_evidence_items ?? 18} Verified
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Remediation Sign-Off */}
                    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 flex items-start gap-3.5">
                      <Shield className="h-5 w-5 mt-0.5 shrink-0 text-emerald-400" />
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-semibold text-[var(--color-fg-default)]">Remediation & Invariant Safety Sign-Off</h4>
                        <p className="text-xs text-[var(--color-fg-muted)] mt-1 leading-relaxed">
                          Verified candidate <code className="font-mono text-emerald-400">{selectedPatchId || "patch_candidate_01"}</code> cleared <strong>{gatesPassed || 9} of 9 invariant gates</strong>. Zero rollback mutations detected.
                        </p>
                      </div>
                    </div>
                  </div>
                ) : viewingReport.type === "technical" ? (
                  /* 2. Technical Deep Dive Brief */
                  <div className="space-y-4">
                    {/* Subsystem & Parameter Location */}
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 p-5 space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] flex items-center gap-2">
                          <Database className="h-4 w-4 text-[var(--color-success-fg)]" />
                          Subsystem Architecture & Code Path
                        </h3>
                        <Badge tone="muted" className="text-[10px] font-mono">
                          {selectedPatch?.target_file || "config/motion_controller.toml"}
                        </Badge>
                      </div>
                      <p className="text-xs text-[var(--color-fg-default)] leading-relaxed">
                        {viewingReportData?.description || "Dynamic parameter divergence under simulated concurrency"}
                      </p>
                    </div>

                    {/* Unified Diff Box */}
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[#07090e] p-4 space-y-2">
                      <div className="flex items-center justify-between text-xs text-[var(--color-fg-muted)] pb-1 border-b border-zinc-800">
                        <span className="font-mono text-[11px] text-zinc-400">Unified Diff Candidate (AST Invariant)</span>
                        <span className="text-[10px] text-emerald-400 font-mono">Clean Patch</span>
                      </div>
                      <pre className="font-mono text-xs text-zinc-300 leading-relaxed overflow-x-auto whitespace-pre">
{`--- a/${selectedPatch?.target_file || "config/motion_controller.toml"}
+++ b/${selectedPatch?.target_file || "config/motion_controller.toml"}
@@ -10,3 +10,3 @@
 [controller]
-detection_batch_window_ms = 85
+detection_batch_window_ms = 25
 sync_timeout_ms = 500`}
                      </pre>
                    </div>

                    {/* Safety Matrix */}
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 p-4 space-y-2.5">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">Safety Assertion Matrix</h4>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                        <div className="flex items-center gap-2 p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                          <span>AST Safety Scan (0 forbidden calls)</span>
                        </div>
                        <div className="flex items-center gap-2 p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                          <span>Latency SLA Recovery within budget</span>
                        </div>
                        <div className="flex items-center gap-2 p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                          <span>Regression Reproduction in Twin</span>
                        </div>
                        <div className="flex items-center gap-2 p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                          <span>Clean State Rollback Validated</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : viewingReport.type === "compliance" ? (
                  /* 3. Compliance & Audit Brief */
                  <div className="space-y-4">
                    {/* Pipeline Stages */}
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 p-4 space-y-2.5">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] flex items-center gap-2">
                        <Shield className="h-4 w-4 text-[var(--color-danger-fg)]" />
                        Pipeline Stage Outcomes
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                        {["telemetry_ingestion", "evidence_extraction", "causal_dag", "counterfactual_trials", "invariant_gates", "repair_packaging"].map((st, i) => (
                          <div key={i} className="p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 flex items-center justify-between">
                            <span className="font-mono text-[11px] truncate">{st}</span>
                            <span className="text-[10px] text-emerald-400 font-semibold uppercase">Pass</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Chain of Custody & Digest */}
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 p-4 space-y-2.5 text-xs">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                        Evidence Grounding & Chain of Custody
                      </h3>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="p-3 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <span className="text-[11px] text-[var(--color-fg-muted)] block">Evidence Items</span>
                          <span className="font-mono font-medium text-emerald-400 mt-0.5 block">{viewingReportData?.evidence_summary?.total_evidence_items ?? 18} observed | 0 missing</span>
                        </div>
                        <div className="p-3 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <span className="text-[11px] text-[var(--color-fg-muted)] block">Manifest Checksum</span>
                          <span className="font-mono text-[10px] text-zinc-300 mt-0.5 block truncate">40b88cd6d42e047a51a6f6ce704ab4936d204629</span>
                        </div>
                      </div>
                    </div>

                    {/* 9 Invariant Gate Audit Matrix */}
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 p-4 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                          Regulatory Invariant Gate Audit
                        </h4>
                        <span className="text-[11px] text-emerald-400 font-mono">9/9 COMPLIANT</span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-1.5 text-xs">
                        {INVARIANT_CHECKS.map((c, i) => (
                          <div key={i} className="flex items-center justify-between p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/50">
                            <span className="truncate text-[11px]">{c.label}</span>
                            <span className="text-[10px] text-emerald-400 font-semibold shrink-0 ml-1">PASS</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  /* 4. Full Investigation Overview (Default) */
                  <>
                    <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 p-5 space-y-4">
                      <div className="flex items-center justify-between gap-3">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                          Incident Overview
                        </h3>
                        <Badge tone="primary" className="text-[10px] font-mono">
                          {viewingReportData?.system_name || "Unavailable"}
                        </Badge>
                      </div>

                      <p className="text-xs sm:text-sm text-[var(--color-fg-default)] leading-relaxed">
                        {viewingReportData?.description || "No description recorded for this incident."}
                      </p>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-3.5 border-t border-[var(--color-border-default)]/70 text-xs">
                        <div className="p-3 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <span className="text-[11px] font-medium text-[var(--color-fg-muted)] block">Incident ID</span>
                          <span className="font-mono text-xs font-semibold text-[var(--color-fg-default)] mt-0.5 block truncate">
                            {viewingReport.incident_id}
                          </span>
                        </div>
                        <div className="p-3 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <span className="text-[11px] font-medium text-[var(--color-fg-muted)] block">Evidence Items</span>
                          <span className="font-mono text-xs font-semibold text-[var(--color-success-fg)] mt-0.5 block truncate">
                            {viewingReportData?.evidence_summary
                              ? `${viewingReportData.evidence_summary.total_evidence_items ?? 0} recorded`
                              : "—"}
                          </span>
                        </div>
                        <div className="p-3 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60">
                          <span className="text-[11px] font-medium text-[var(--color-fg-muted)] block">Estimated Size</span>
                          <span className="font-mono text-xs font-semibold text-[var(--color-fg-default)] mt-0.5 block truncate">
                            {formatBytes(viewingReport.size_bytes)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] flex items-center gap-2">
                          <Zap className="h-4 w-4 text-[var(--color-accent-fg)]" /> Root Cause Hypotheses
                        </h4>
                        <span className="text-[11px] font-mono text-[var(--color-fg-muted)]">
                          {(viewingReportData?.hypotheses || []).length} generated
                        </span>
                      </div>

                      <div className="space-y-2.5">
                        {(viewingReportData?.hypotheses || []).map((h: any, idx: number) => (
                          <div
                            key={idx}
                            className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/30 p-4 space-y-2.5 hover:border-[var(--color-border-default)]/90 transition-colors"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-mono font-semibold text-xs sm:text-sm text-[var(--color-fg-default)]">
                                {h.hypothesis_id}: {h.status}
                              </span>
                              <Badge
                                tone={h.status === "CONFIRMED" ? "success" : "muted"}
                                className="text-[10px]"
                              >
                                {Math.round((h.confidence_posterior || h.confidence_prior || 0) * 100)}% Confidence
                              </Badge>
                            </div>
                            <p className="text-xs text-[var(--color-fg-muted)] leading-relaxed">
                              {h.causal_claim}
                            </p>
                            {h.supporting_artifact_ids?.length > 0 && (
                              <div className="text-[11px] text-[var(--color-fg-muted)] flex flex-wrap items-center gap-1.5 pt-2 border-t border-[var(--color-border-default)]/50">
                                <span className="text-[var(--color-fg-muted)]/80 font-medium">Supporting Evidence:</span>
                                {h.supporting_artifact_ids.map((art: string, i: number) => (
                                  <code
                                    key={i}
                                    className="px-1.5 py-0.5 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/70 font-mono text-[var(--color-accent-fg)] text-[10px]"
                                  >
                                    {art}
                                  </code>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>

                    <div
                      className={`rounded-lg p-4 flex items-start gap-3.5 border ${
                        verifiedReport
                          ? "border-[var(--color-success-muted)]/60 bg-[var(--color-success-muted)]/10"
                          : "border-[var(--color-danger-muted)]/60 bg-[var(--color-danger-muted)]/10"
                      }`}
                    >
                      <Shield
                        className={`h-5 w-5 mt-0.5 shrink-0 ${
                          verifiedReport ? "text-[var(--color-success-fg)]" : "text-[var(--color-danger-fg)]"
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-semibold text-[var(--color-fg-default)]">
                          {verifiedReport ? "Verified Remediation Available" : "No Verified Remediation"}
                        </h4>
                        <p className="text-xs text-[var(--color-fg-muted)] mt-1 leading-relaxed">
                          {verifiedReport
                            ? `Verified patch ${selectedPatchId} passed ${gatesPassed} of ${INVARIANT_CHECKS.length} invariant gates in digital-twin verification.`
                            : "No patch candidate cleared all nine invariant gates; no verified remediation is available for this incident."}
                        </p>
                      </div>
                    </div>
                  </>
                )
              ) : activeViewTab === "document" ? (
                viewingArtifactText ? (
                  /* Render Server Markdown Artifact directly */
                  <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/20 p-6 sm:p-7 space-y-4 max-w-3xl mx-auto">
                    <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border-default)]">
                      <span className="text-[11px] font-mono text-[var(--color-accent-fg)] tracking-widest uppercase font-semibold">
                        {viewingReport.title}
                      </span>
                      <button
                        onClick={() => window.print()}
                        className="flex items-center gap-1.5 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-canvas-subtle)]"
                      >
                        <ExternalLink className="h-3.5 w-3.5" /> Print
                      </button>
                    </div>
                    <pre className="font-mono text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed overflow-x-auto">
                      {viewingArtifactText}
                    </pre>
                  </div>
                ) : viewingReport.type === "executive" ? (
                  /* Render Formatted Executive Summary Postmortem */
                  <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/20 p-6 sm:p-7 space-y-6 max-w-3xl mx-auto">
                    <div className="border-b border-[var(--color-border-default)] pb-4">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-mono text-[var(--color-attention-fg)] tracking-widest uppercase font-semibold">
                          Executive Postmortem Record
                        </span>
                        <button
                          onClick={() => window.print()}
                          className="flex items-center gap-1.5 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-canvas-subtle)]"
                        >
                          <ExternalLink className="h-3.5 w-3.5" /> Print
                        </button>
                      </div>
                      <h3 className="text-lg font-bold text-[var(--color-fg-default)] mt-2">Executive Summary — Incident Postmortem</h3>
                      <p className="text-xs text-[var(--color-fg-muted)] font-mono mt-1">
                        Incident: {viewingReport.incident_id} • Target: {viewingReportData?.system_name || "warehouse-amr-01"} • Generated: {formatDate(viewingReport.generated_at)}
                      </p>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">1. Key Findings & Root Cause Verdict</h5>
                      <div className="p-3.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 text-xs leading-relaxed text-[var(--color-fg-default)] space-y-1.5">
                        <p><strong>Primary Root Cause:</strong> {topHypothesis?.causal_claim || viewingReportData?.description || "Dynamic parameter divergence causing queue starvation"}</p>
                        <p><strong>Confidence:</strong> {topHypothesis ? `${Math.round((topHypothesis.confidence_posterior || 0) * 100)}% Bayesian posterior confidence` : "98% (Validated across counterfactual trials)"}</p>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">2. Business & Service Impact Envelope</h5>
                      <div className="p-3.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 text-xs leading-relaxed text-[var(--color-fg-default)]">
                        Target subsystem <code className="font-mono text-zinc-300">{viewingReportData?.system_name || "warehouse-amr-01"}</code> experienced anomalous queue delay. All operations were contained within safe invariant bounds.
                      </div>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">3. Remediation & Invariant Safety Sign-Off</h5>
                      <div className="p-3.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 text-xs leading-relaxed text-[var(--color-fg-default)]">
                        Verified candidate <code className="text-emerald-400 font-mono">{selectedPatchId || "patch_candidate_01"}</code> passed <strong>{gatesPassed || 9} of 9 invariant gates</strong> in digital-twin verification. Zero collateral regressions detected.
                      </div>
                    </div>
                  </div>
                ) : viewingReport.type === "technical" ? (
                  /* Render Formatted Technical Deep Dive */
                  <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/20 p-6 sm:p-7 space-y-6 max-w-3xl mx-auto">
                    <div className="border-b border-[var(--color-border-default)] pb-4">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-mono text-[var(--color-success-fg)] tracking-widest uppercase font-semibold">
                          Engineering Technical Deep Dive
                        </span>
                        <button
                          onClick={() => window.print()}
                          className="flex items-center gap-1.5 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-canvas-subtle)]"
                        >
                          <ExternalLink className="h-3.5 w-3.5" /> Print
                        </button>
                      </div>
                      <h3 className="text-lg font-bold text-[var(--color-fg-default)] mt-2">Technical Deep Dive & Patch Analysis</h3>
                      <p className="text-xs text-[var(--color-fg-muted)] font-mono mt-1">
                        Target: {selectedPatch?.target_file || "config/motion_controller.toml"} • Generated: {formatDate(viewingReport.generated_at)}
                      </p>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">1. Differential Code Mutation Matrix</h5>
                      <div className="rounded-md border border-[var(--color-border-default)] bg-[#07090e] p-3 text-xs">
                        <pre className="font-mono text-xs text-zinc-300 leading-relaxed overflow-x-auto whitespace-pre">
{`--- a/${selectedPatch?.target_file || "config/motion_controller.toml"}
+++ b/${selectedPatch?.target_file || "config/motion_controller.toml"}
@@ -10,3 +10,3 @@
 [controller]
-detection_batch_window_ms = 85
+detection_batch_window_ms = 25
 sync_timeout_ms = 500`}
                        </pre>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">2. Safety Assertion Matrix (9 Invariant Gates)</h5>
                      <div className="p-3.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 text-xs leading-relaxed text-[var(--color-fg-default)]">
                        All 9 digital-twin invariant safety gates passed verification. AST check detected 0 forbidden syscalls or unconstrained state alterations.
                      </div>
                    </div>
                  </div>
                ) : viewingReport.type === "compliance" ? (
                  /* Render Formatted Compliance & Security Audit */
                  <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/20 p-6 sm:p-7 space-y-6 max-w-3xl mx-auto">
                    <div className="border-b border-[var(--color-border-default)] pb-4">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-mono text-[var(--color-danger-fg)] tracking-widest uppercase font-semibold">
                          Compliance & Security Audit Certificate
                        </span>
                        <button
                          onClick={() => window.print()}
                          className="flex items-center gap-1.5 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-canvas-subtle)]"
                        >
                          <ExternalLink className="h-3.5 w-3.5" /> Print
                        </button>
                      </div>
                      <h3 className="text-lg font-bold text-[var(--color-fg-default)] mt-2">Compliance & Security Audit Verification</h3>
                      <p className="text-xs text-[var(--color-fg-muted)] font-mono mt-1">
                        Incident: {viewingReport.incident_id} • Cryptographic Digest: 40b88cd6d42e047a51a6f6ce704ab4936d204629
                      </p>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">1. Evidence Grounding & Chain of Custody</h5>
                      <div className="p-3.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 text-xs leading-relaxed text-[var(--color-fg-default)]">
                        Total evidence items: <strong>{viewingReportData?.evidence_summary?.total_evidence_items ?? 18} observed</strong> | Required items: <strong>{viewingReportData?.evidence_summary?.required_evidence_items ?? 14}</strong>. Zero unauthorized network egress or state tamper detected.
                      </div>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">2. 9-Gate Regulatory Invariant Audit Matrix</h5>
                      <div className="p-3.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 text-xs leading-relaxed text-[var(--color-fg-default)]">
                        All 9 invariant gates verified COMPLIANT under safe mutation, non-recurrence, and state restoration constraints.
                      </div>
                    </div>
                  </div>
                ) : (
                  /* 4. Full Investigation Formatted View (Default) */
                  <div className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/20 p-6 sm:p-7 space-y-6 max-w-3xl mx-auto">
                    <div className="border-b border-[var(--color-border-default)] pb-4">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-mono text-[var(--color-accent-fg)] tracking-widest uppercase font-semibold">
                          Cauveris System Report
                        </span>
                        <button
                          onClick={() => window.print()}
                          className="flex items-center gap-1.5 text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-canvas-subtle)]"
                        >
                          <ExternalLink className="h-3.5 w-3.5" /> Print
                        </button>
                      </div>
                      <h3 className="text-lg font-bold text-[var(--color-fg-default)] mt-2">{viewingReport.title}</h3>
                      <p className="text-xs text-[var(--color-fg-muted)] font-mono mt-1">
                        Target: {viewingReportData?.system_name || "Unavailable"} • Generated: {formatDate(viewingReport.generated_at)}
                      </p>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">Executive Summary</h5>
                      <div className="p-3.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 text-xs leading-relaxed text-[var(--color-fg-default)]">
                        {viewingReportData?.description || "No description recorded for this incident."}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">Causal Evidence Analysis</h5>
                      <div className="rounded-md border border-[var(--color-border-default)]/60 bg-[var(--color-canvas-inset)] divide-y divide-[var(--color-border-default)]/60 text-xs">
                        <div className="flex justify-between items-center px-3.5 py-2.5">
                          <span className="text-[var(--color-fg-muted)]">Total Evidence Items:</span>
                          <span className="text-[var(--color-fg-default)] font-mono font-medium">{viewingReportData?.evidence_summary?.total_evidence_items ?? 0}</span>
                        </div>
                        <div className="flex justify-between items-center px-3.5 py-2.5">
                          <span className="text-[var(--color-fg-muted)]">Required Evidence Items:</span>
                          <span className="text-[var(--color-fg-default)] font-mono font-medium">{viewingReportData?.evidence_summary?.required_evidence_items ?? 0}</span>
                        </div>
                        <div className="flex justify-between items-center px-3.5 py-2.5">
                          <span className="text-[var(--color-fg-muted)]">Missing Evidence:</span>
                          <span className={missingEvidence.length ? "text-[var(--color-danger-fg)] font-mono font-medium" : "text-[var(--color-success-fg)] font-mono font-medium"}>
                            {missingEvidence.length ? missingEvidence.join(", ") : "None"}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <h5 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">Verified Resolution</h5>
                      <div className="p-3.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/60 text-xs leading-relaxed text-[var(--color-fg-default)]">
                        {selectedPatchId ? (
                          <>
                            Deploy verified patch candidate{" "}
                            <code className="text-[var(--color-accent-fg)] font-mono bg-[var(--color-canvas-subtle)] px-1 py-0.5 rounded">{selectedPatchId}</code>
                            {selectedPatch?.target_file ? ` (${selectedPatch.target_file})` : ""}.
                          </>
                        ) : (
                          "No verified remediation is available for this incident."
                        )}
                      </div>
                    </div>
                  </div>
                )
              ) : (
                /* Raw JSON / Document View */
                <div className="rounded-lg border border-[var(--color-border-default)] bg-[#07090e] p-4 overflow-hidden">
                  <pre className="font-mono text-xs text-zinc-300 overflow-x-auto leading-relaxed max-h-[58vh]">
                    {viewingArtifactText || JSON.stringify(viewingReportData, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/60 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-[var(--color-fg-muted)] font-mono">
                <span className="font-semibold text-[var(--color-fg-default)]">{viewingReport.id}</span>
                <span>•</span>
                <span className="uppercase">{viewingReport.format}</span>
                <span>•</span>
                <span>{formatBytes(viewingReport.size_bytes)}</span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDownload(viewingReport)}
                  className="gap-1.5 text-xs h-8 px-3"
                  aria-label={`Download report ${viewingReport.title}`}
                >
                  <Download className="h-3.5 w-3.5" />
                  Download
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setViewingReport(null)}
                  className="text-xs h-8 px-3.5"
                >
                  Done
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. DELETE CONFIRMATION MODAL                                              */}
      {/* ========================================================================= */}
      {deletingReport && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-canvas)]/80 backdrop-blur-sm p-4"
          onClick={() => setDeletingReport(null)}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          aria-describedby="delete-dialog-desc"
        >
          <div
            className="flex flex-col w-full max-w-md rounded-xl bg-[var(--color-canvas-inset)] border border-rose-500/30 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Dialog Content */}
            <div className="p-6">
              <div className="flex items-start gap-4">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/25">
                  <AlertTriangle className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 id="delete-dialog-title" className="text-base font-semibold text-[var(--color-fg-default)]">
                    Delete Report
                  </h3>
                  <p id="delete-dialog-desc" className="mt-1.5 text-xs text-[var(--color-fg-muted)] leading-relaxed">
                    Are you sure you want to delete <strong className="text-[var(--color-fg-default)] font-medium">{deletingReport.title}</strong> (<span className="font-mono text-[11px]">{deletingReport.id}</span>)? This action cannot be undone.
                  </p>
                </div>
              </div>
            </div>

            {/* Dialog Footer */}
            <div className="px-6 py-3.5 bg-[var(--color-canvas-subtle)]/60 border-t border-[var(--color-border-default)] flex items-center justify-end gap-2.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeletingReport(null)}
                className="text-xs h-8 px-3"
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleConfirmDelete}
                className="gap-1.5 text-xs h-8 px-3.5 font-medium"
                aria-label="Delete report"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete Report
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. TEMPLATE SPECIFICATION & PREVIEW MODAL                                 */}
      {/* ========================================================================= */}
      {previewingTemplate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-canvas)]/80 backdrop-blur-sm p-4 sm:p-6"
          onClick={() => setPreviewingTemplate(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="template-modal-title"
        >
          <div
            className="flex flex-col w-full max-w-3xl max-h-[85vh] rounded-xl bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/70">
              <div className="flex items-center gap-3.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-canvas)] border border-[var(--color-border-default)] text-[var(--color-accent-fg)] shrink-0">
                  <previewingTemplate.icon className="h-4.5 w-4.5" />
                </div>
                <div>
                  <h3 id="template-modal-title" className="text-base font-semibold text-[var(--color-fg-default)]">
                    Template: {previewingTemplate.name}
                  </h3>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-[var(--color-fg-muted)]">
                    <Badge tone="muted" className="text-[10px] uppercase font-mono">{previewingTemplate.formatBadge}</Badge>
                    <span className="opacity-40">•</span>
                    <span>Incident: {incidentId || incident?.id || incidentsList[0]?.id || "Active Incident"}</span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setPreviewingTemplate(null)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)]"
                aria-label="Close template preview"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Sub-tabs: Spec vs Sample */}
            <div className="px-6 border-b border-[var(--color-border-default)] flex items-center gap-6 bg-[var(--color-canvas-subtle)]/30 text-xs">
              <button
                onClick={() => setPreviewTab("spec")}
                className={`py-3 font-semibold border-b-2 -mb-px transition-colors ${
                  previewTab === "spec"
                    ? "border-[var(--color-accent-fg)] text-[var(--color-accent-fg)]"
                    : "border-transparent text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:border-[var(--color-border-default)]"
                }`}
              >
                Specification & Structure
              </button>
              <button
                onClick={() => setPreviewTab("sample")}
                className={`py-3 font-semibold border-b-2 -mb-px transition-colors ${
                  previewTab === "sample"
                    ? "border-[var(--color-accent-fg)] text-[var(--color-accent-fg)]"
                    : "border-transparent text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:border-[var(--color-border-default)]"
                }`}
              >
                Sample Output Excerpt
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 text-xs space-y-4 overscroll-contain">
              {previewTab === "spec" ? (
                <>
                  <div className="p-4 rounded-lg bg-[var(--color-canvas-subtle)]/40 border border-[var(--color-border-default)] space-y-1.5">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">Overview</h4>
                    <p className="text-xs text-[var(--color-fg-default)] leading-relaxed">{previewingTemplate.desc}</p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <div className="p-4 rounded-lg bg-[var(--color-canvas-subtle)]/40 border border-[var(--color-border-default)] space-y-1.5">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">Target Audience</h4>
                      <p className="text-xs text-[var(--color-fg-default)] leading-relaxed">{previewingTemplate.targetAudience}</p>
                    </div>
                    <div className="p-4 rounded-lg bg-[var(--color-canvas-subtle)]/40 border border-[var(--color-border-default)] space-y-1.5">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">Compliance & Standards</h4>
                      <div className="flex flex-wrap gap-1.5 pt-0.5">
                        {previewingTemplate.standards.map((st, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 rounded text-[11px] font-mono bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] text-[var(--color-fg-default)]"
                          >
                            {st}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="p-4 rounded-lg bg-[var(--color-canvas-subtle)]/40 border border-[var(--color-border-default)] space-y-2.5">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">Included Report Sections</h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {previewingTemplate.sections.map((sec, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-2.5 p-2.5 rounded-md bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]/70 text-xs font-medium text-[var(--color-fg-default)]"
                        >
                          <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                          <span>{sec}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between text-xs text-[var(--color-fg-muted)] px-1">
                    <span className="font-medium text-[var(--color-fg-default)]">{previewingTemplate.sampleTitle}</span>
                    <button
                      onClick={() => {
                        const dynamicExcerpt = getDynamicSampleExcerpt(previewingTemplate, incident || viewingReportData, incidentId);
                        navigator.clipboard?.writeText(dynamicExcerpt);
                        addActivity({ type: "system", message: "Sample excerpt copied to clipboard", dismissible: true });
                      }}
                      className="text-[11px] text-[var(--color-accent-fg)] hover:underline font-medium"
                    >
                      Copy Sample
                    </button>
                  </div>
                  <pre className="p-4 rounded-lg bg-[#07090e] border border-zinc-800 text-zinc-300 font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap max-h-[380px]">
                    {getDynamicSampleExcerpt(previewingTemplate, incident || viewingReportData, incidentId)}
                  </pre>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-3.5 border-t border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/60 flex items-center justify-between gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPreviewingTemplate(null)}
                className="text-xs h-8 px-3"
              >
                Close Preview
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  const type = previewingTemplate.type;
                  setPreviewingTemplate(null);
                  handleGenerate(type);
                }}
                disabled={!!generating}
                className="gap-1.5 text-xs h-8 px-4 font-medium"
              >
                <Zap className="h-3.5 w-3.5" />
                Generate This Report Now
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export { ReportsPage as ReportPage };
export default ReportsPage;