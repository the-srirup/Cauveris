"use client";

import { Button } from '@/components/ui';
import { Card, Stat, Progress, Badge, KV, PageHeader } from '@/components/ui';

export default function MissionControl() {
  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      {/* Header */}
      <PageHeader
        title="Mission Control"
        subtitle="Autonomous reality debugger for AI-powered robotic systems"
        badge={<Badge tone="primary">System Ready</Badge>}
      />

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Incident Status */}
        <Card title="Incident Status">
          <Stat
            label="Current State"
            value="RECEIVED"
            sub="Awaiting evidence"
            trend="flat"
          />
        </Card>

        {/* Evidence Completeness */}
        <Card title="Evidence Completeness">
          <Stat
            label="Collected Artifacts"
            value="0"
            sub="/ 12 required"
            trend="flat"
          />
          <Progress value={0} tone="primary" className="mt-3" />
          <div className="mt-2 text-xs text-muted">
            Loading incident bundle...
          </div>
        </Card>

        {/* Sandbox Budget */}
        <Card title="Sandbox Budget">
          <Stat
            label="Compute Units"
            value="0.00"
            sub="/ 50.00 allocated"
            trend="flat"
          />
          <Progress value={0} tone="secondary" className="mt-3" />
          <div className="mt-2 flex justify-between text-xs text-muted">
            <span>Available: 50.00 CU</span>
            <span>Used: 0.00 CU</span>
          </div>
        </Card>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Controls & Status */}
        <div className="space-y-6">
          {/* Workflow Controls */}
          <Card title="Workflow Controls">
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <span className="text-sm font-medium text-muted">Current Stage:</span>
                <span className="text-sm font-mono text-primary">RECEIVED</span>
              </div>
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <span className="text-sm font-medium text-muted">Model Route:</span>
                <span className="text-sm font-mono text-success">
                  Local Fixtures
                </span>
              </div>
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <span className="text-sm font-medium text-muted">Sandbox Status:</span>
                <span className="text-sm font-mono text-muted">
                  Idle
                </span>
              </div>
              <div className="flex justify-end space-x-3">
                <Button variant="outline" onClick={() => alert('Upload incident')}>
                  Upload Incident
                </Button>
                <Button variant="primary" onClick={() => alert('Load golden incident')}>
                  Load Golden Incident
                </Button>
              </div>
            </div>
          </Card>

          {/* Mode Toggles */}
          <Card title="Operational Modes">
            <div className="space-y-3">
              <label className="flex items-center gap-3 text-sm text-muted cursor-select">
                <input type="checkbox" className="h-4 w-4 text-primary" />
                Judge Mode
              </label>
              <label className="flex items-center gap-3 text-sm text-muted cursor-select">
                <input type="checkbox" className="h-4 w-4 text-primary" />
                Engineer Mode
              </label>
            </div>
          </Card>
        </div>

        {/* Right: Visual Twin & Timeline */}
        <div className="space-y-6">
          {/* Digital Twin */}
          <Card title="Digital Twin / Replay">
            <div className="aspect-video w-full bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative">
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="space-y-4 text-center">
                  <div className="w-24 h-24 bg-primary/10 rounded-full flex items-center justify-center mb-4 ring-2 ring-primary/20">
                    <svg className="w-10 h-10 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3"></path>
                    </svg>
                  </div>
                  <p className="text-lg font-medium text-white">Robot Digital Twin</p>
                  <p className="text-sm text-muted">
                    Waiting for incident data...
                  </p>
                  <div className="w-full h-0.5 bg-primary/20 mx-4 my-6" />
                  <div className="flex items-center gap-3 justify-center text-xs text-muted">
                    <div className="flex items-center gap-1">
                      <div className="w-2 h-2 bg-success rounded-full" />
                      <span>Sensors Nominal</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-2 h-2 bg-primary/20 rounded border border-primary/50" />
                      <span>Simulation Ready</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Card>

          {/* Incident Timeline Preview */}
          <Card title="Incident Timeline">
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 bg-primary/20 rounded-full border border-primary/20 flex-shrink-0 mt-1"></div>
                <div className="space-y-1">
                  <p className="font-medium text-muted">Incident Received</p>
                  <p className="text-sm text-xs">2026-09-20 14:30:22 UTC</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-px h-3 bg-primary/20"></div>
                <div className="space-y-1">
                  <p className="font-medium text-muted">Evidence Validation</p>
                  <p className="text-sm text-xs">Pending</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-px h-3 bg-primary/20"></div>
                <div className="space-y-1">
                  <p className="font-medium text-muted">Timeline Construction</p>
                  <p className="text-sm text-xs">Pending</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-px h-3 bg-primary/20"></div>
                <div className="space-y-1">
                  <p className="font-medium text-muted">Hypothesis Generation</p>
                  <p className="text-sm text-xs">Pending</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 bg-primary/20 rounded-full border border-primary/20 flex-shrink-0 mt-1"></div>
                <div className="space-y-1">
                  <p className="font-medium text-muted">Analysis Complete</p>
                  <p className="text-sm text-xs">Pending</p>
                </div>
              </div>
            </div>
          </Card>
        </div>
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
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3 3 0 014.438 0 3.42 3.42 0 001.946.806 3 3 0 014.438 0 3.42 3.42 0 001.946.806V16a3 3 0 01-3 3H6a3 3 0 01-3 3V4.697z"></path>
            </svg>
            <span>Version 1.0.0 • Build 2026.09.20</span>
          </div>
        </div>
      </footer>
    </div>
  );
}