"use client";

import { Button } from '@/components/ui';
import { Card, Stat, Badge, KV, PageHeader } from '@/components/ui';

export default function EvidenceVault() {
  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      {/* Header */}
      <PageHeader
        title="Evidence Vault"
        subtitle="Complete provenance-linked artifact repository"
        badge={<Badge tone="success">All Claims Evidenced</Badge>}
      />

      {/* Main Content */}
      <div className="space-y-8">
        {/* Claims Summary */}
        <Card title="Verified Claims Summary">
          <div className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-3">
              <Stat label="Total Claims" value="12" sub="Evidence-backed" trend="flat" />
              <Stat label="Linked Artifacts" value="28" sub="Total provenance links" trend="flat" />
              <Stat label="Verification Status" value="100%" sub="Claims evidenced" trend="success" />
            </div>
          </div>
        </Card>

        {/* Artifact Browser */}
        <Card title="Artifact Inventory">
          <div className="space-y-4">
            {/* Filter Controls */}
            <div className="flex flex-wrap items-center gap-4 mb-4">
              <input
                type="text"
                placeholder="Search artifacts..."
                className="bg-[var(--color-surface)] text-primary border border-primary/30 rounded px-4 py-2 w-48"
              />
              <select
                className="bg-[var(--color-surface)] text-primary border border-primary/30 rounded px-4 py-2"
              >
                <option value="all">All Types</option>
                <option value="hypothesis">Hypotheses</option>
                <option value="experiment">Experiments</option>
                <option value="patch">Patches</option>
                <option value="report">Reports</option>
              </select>
              <select
                className="bg-[var(--color-surface)] text-primary border border-primary/30 rounded px-4 py-2"
              >
                <option value="status">Status</option>
                <option value="OBSERVED">OBSERVED</option>
                <option value="INFERRED">INFERRED</option>
                <option value="REPRODUCED">REPRODUCED</option>
                <option value="VERIFIED_IN_SANDBOX">VERIFIED_IN_SANDBOX</option>
              </select>
            </div>

            {/* Artifact List */}
            <div className="space-y-4">
              {/* Artifact Item */}
              <div className="flex items-start gap-4 p-4 bg-[var(--color-surface)] rounded-lg border border-primary/20">
                <div className="flex-shrink-0 w-10 h-10 bg-primary/20 text-primary flex items-center justify-center rounded-lg">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m2 0a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-primary">hyp-001: Batching Window Increase</h3>
                  <p className="text-sm text-muted">
                    Hypothesis: Increased dynamic batching window caused inference P99 latency to exceed freshness budget
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge tone="secondary">Status: REPRODUCED</Badge>
                    <Badge tone="primary">ID: hyp-001</Badge>
                    <Badge tone="primary">Type: Hypothesis</Badge>
                  </div>
                </div>
                <div className="flex-shrink-0 text-right text-xs text-muted">
                  Linked to:<br/>4 artifacts
                </div>
              </div>

              {/* Artifact Item */}
              <div className="flex items-start gap-4 p-4 bg-[var(--color-surface)] rounded-lg border border-primary/20">
                <div className="flex-shrink-0 w-10 h-10 bg-primary/20 text-primary flex items-center justify-center rounded-lg">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3M6 6h.01M18 6h.01M6 12h.01M18 12h.01M6 18h.01M18 18h.01"></path>
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-primary">exp-001: Batching Window Experiment</h3>
                  <p className="text-sm text-muted">
                    Experiment: Reduced dynamic batching window from 200ms to 100ms
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge tone="secondary">Status: COMPLETED</Badge>
                    <Badge tone="primary">ID: exp-001</Badge>
                    <Badge tone="primary">Type: Experiment</Badge>
                  </div>
                </div>
                <div className="flex-shrink-0 text-right text-xs text-muted">
                  Linked to:<br/>3 artifacts
                </div>
              </div>

              {/* Artifact Item */}
              <div className="flex items-start gap-4 p-4 bg-[var(--color-surface)] rounded-lg border border-primary/20">
                <div className="flex-shrink-0 w-10 h-10 bg-success/20 text-success flex items-center justify-center rounded-lg">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3"></path>
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-primary">patch-001: Batching Window Fix</h3>
                  <p className="text-sm text-muted">
                    Patch: Set batching window back to 100ms
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge tone="success">Status: VERIFIED</Badge>
                    <Badge tone="primary">ID: patch-001</Badge>
                    <Badge tone="primary">Type: Patch</Badge>
                  </div>
                </div>
                <div className="flex-shrink-0 text-right text-xs text-muted">
                  Linked to:<br/>5 artifacts
                </div>
              </div>

              {/* Artifact Item */}
              <div className="flex items-start gap-4 p-4 bg-[var(--color-surface)] rounded-lg border border-primary/20">
                <div className="flex-shrink-0 w-10 h-10 bg-primary/20 text-primary flex items-center justify-center rounded-lg">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10V6m0 0l3-3m-3 3"></path>
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-primary">Incident Report CAU-0001</h3>
                  <p className="text-sm text-muted">
                    Complete investigation report with evidence chain
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge tone="secondary">Status: COMPLETED</Badge>
                    <Badge tone="primary">ID: incident-CAU-0001</Badge>
                    <Badge tone="primary">Type: Report</Badge>
                  </div>
                </div>
                <div className="flex-shrink-0 text-right text-xs text-muted">
                  Linked to:<br/>12 artifacts
                </div>
              </div>
            </div>
          </div>
        </Card>

        {/* Download Section */}
        <Card title="Download Review Package">
          <div className="space-y-4">
            <p className="text-sm text-muted">
              Download the complete evidence-backed pull-request package for human review and approval.
            </p>
            <div className="flex items-center justify-end gap-4">
              <Button variant="outline" onClick={() => alert('Download full report')}>
                Download Full Report
              </Button>
              <Button variant="primary" onClick={() => alert('Download patch package')}>
                Download Patch Package
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {/* Footer */}
      <footer className="mt-12 pt-8 border-t border-white/10">
        <div className="flex flex-col lg:flex-row lg:justify-between lg:items-center gap-4 text-xs text-muted">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3M6 16l6-6 6 6"></path>
            </svg>
            <span>Powered by Nebius x NVIDIA Global AI Hackathon</span>
          </div>
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3 3 0 014.438 0 3.42 3.42 0 001.946.806 3 3 0 001.946.806V16a3 3 0 01-3 3H6a3 3 0 01-3 3V4.697z"></path>
            </svg>
            <span>Version 1.0.0 • Build 2026.09.20</span>
          </div>
        </div>
      </footer>
    </div>
  );
}