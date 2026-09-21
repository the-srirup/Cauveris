"use client";

import { Button } from '@/components/ui';
import { Card, Stat, Badge, KV, PageHeader } from '@/components/ui';

export default function VictoryReplay() {
  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      {/* Header */}
      <PageHeader
        title="Victory Replay"
        subtitle="Before/after validation and rollback confirmation"
        badge={<Badge tone="success">Patch Validated</Badge>}
      />

      {/* Main Content */}
      <div className="space-y-8">
        {/* Side-by-side Replays */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Before Patch */}
          <Card title="Pre-Patch Robot Replay">
            <div className="aspect-video w-full bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative">
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="space-y-4 text-center">
                  <div className="w-24 h-24 bg-danger/10 rounded-full flex items-center justify-center mb-4 ring-2 ring-danger/20" />
                  <p className="text-lg font-medium text-white">
                    Robot stops due to emergency stop
                  </p>
                </div>
              </div>
            </div>
          </Card>

          {/* After Patch */}
          <Card title="Post-Patch Robot Replay">
            <div className="aspect-video w-full bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative">
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="space-y-4 text-center">
                  <div className="w-24 h-24 bg-success/10 rounded-full flex items-center justify-center mb-4 ring-2 ring-success/20" />
                  <p className="text-lg font-medium text-white">
                    Robot completes route successfully
                  </p>
                </div>
              </div>
            </div>
          </Card>
        </div>

        {/* Metrics Comparison */}
        <Card title="Key Metrics Comparison">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-white/10">
              <thead>
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Metric
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Before Patch
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    After Patch
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase tracking-wider">
                    Improvement
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="px-6 py-4 text-sm font-medium text-muted">
                    Failure Count
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-danger">10/10</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">0/10</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">100%</td>
                </tr>
                <tr>
                  <td className="px-6 py-4 text-sm font-medium text-muted">
                    Detection Age (P99)
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-danger">140ms</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">90ms</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">35%</td>
                </tr>
                <tr>
                  <td className="px-6 py-4 text-sm font-medium text-muted">
                    Inference P99 Latency
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-danger">180ms</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">110ms</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">39%</td>
                </tr>
                <tr>
                  <td className="px-6 py-4 text-sm font-medium text-muted">
                    Control Loop P95
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-muted">60ms</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">45ms</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">25%</td>
                </tr>
                <tr>
                  <td className="px-6 py-4 text-sm font-medium text-muted">
                    Safety Invariant State
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-danger">Violated</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">Nominal</td>
                  <td className="px-6 py-4 text-sm font-medium text-success">Restored</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Trial Progress & Rollback */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Trial Progress */}
          <Card title="Trial Progress">
            <div className="space-y-4">
              <div className="flex justify-between items-start mb-2">
                <span className="text-sm font-medium text-muted">Trials Completed:</span>
                <span className="font-mono text-primary">10 / 10</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <span className="text-sm font-medium text-muted">Success Rate:</span>
                <span className="font-mono text-success">100%</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <span className="text-sm font-medium text-muted">Average Latency:</span>
                <span className="font-mono text-success">95ms</span>
              </div>
              <div className="flex justify-between items-start">
                <span className="text-sm font-medium text-muted">Latency Jitter:</span>
                <span className="font-mono">5ms</span>
              </div>
            </div>
          </Card>

          {/* Rollback Result */}
          <Card title="Rollback Verification">
            <div className="space-y-4">
              <p className="text-sm text-muted">
                Rollback to pre-patch state successfully restores original failure behavior for validation.
              </p>
              <div className="mt-4 flex justify-end">
                <Button variant="danger" onClick={() => alert('Test rollback')}>
                  Test Rollback
                </Button>
              </div>
            </div>
          </Card>
        </div>
      }

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