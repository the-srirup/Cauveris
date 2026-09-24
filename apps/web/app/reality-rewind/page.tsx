"use client";

import { Button, Card, Badge, KV, PageHeader } from "@/components/ui";

export default function RealityRewind() {
  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      {/* Header */}
      <PageHeader
        title="Reality Rewind"
        subtitle="Synchronized multi-source timeline reconstruction"
        badge={<Badge tone="success">Sandbox Verified</Badge>}
      />

      {/* Main Content */}
      <div className="space-y-8">
        {/* Synchronized Timeline */}
        <Card title="Synchronized Timeline">
          <div className="space-y-6">
            {/* Timeline Lanes */}
            <div className="space-y-4">
              <div className="flex items-center gap-4 py-3 border-b border-white/5">
                <div className="w-3 h-3 bg-primary rounded-full" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-muted">Deployment Events</p>
                  <p className="text-xs font-mono text-primary">v42 → v41</p>
                </div>
                <div className="flex-1 h-0.5 bg-primary/20" />
                <Badge tone="danger">Configuration Drift</Badge>
              </div>

              <div className="flex items-center gap-4 py-3 border-b border-white/5">
                <div className="w-3 h-3 bg-primary rounded-full" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-muted">Cloud Requests</p>
                  <p className="text-xs font-mono text-primary">150ms latency</p>
                </div>
                <div className="flex-1 h-0.5 bg-primary/20" />
                <Badge tone="danger">Budget Exceeded</Badge>
              </div>

              <div className="flex items-center gap-4 py-3 border-b border-white/5">
                <div className="w-3 h-3 bg-primary rounded-full" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-muted">Detection Publication</p>
                  <p className="text-xs font-mono text-primary">Age: 140ms (over budget)</p>
                </div>
                <div className="flex-1 h-0.5 bg-primary/20" />
                <Badge tone="danger">Freshness Violation</Badge>
              </div>

              <div className="flex items-center gap-4 py-3 border-b border-white/5">
                <div className="w-3 h-3 bg-primary rounded-full" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-muted">TF Events</p>
                  <p className="text-xs font-mono text-danger">Lookup Failed</p>
                </div>
                <div className="flex-1 h-0.5 bg-primary/20" />
                <Badge tone="danger">Critical Failure</Badge>
              </div>

              <div className="flex items-center gap-4 py-3 border-b border-white/5">
                <div className="w-3 h-3 bg-primary rounded-full" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-muted">Controller Latency</p>
                  <p className="text-xs font-mono text-danger">Deadline Missed</p>
                </div>
                <div className="flex-1 h-0.5 bg-primary/20" />
                <Badge tone="danger">Control Failure</Badge>
              </div>

              <div className="flex items-center gap-4 py-3">
                <div className="w-3 h-3 bg-primary rounded-full" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-muted">Safety State</p>
                  <p className="text-xs font-mono text-danger">EMERGENCY STOP</p>
                </div>
                <div className="flex-1 h-0.5 bg-primary/20" />
                <Badge tone="danger">Safety Tripped</Badge>
              </div>
            </div>

            {/* Timeline Scrubber */}
            <div className="mt-6">
              <div className="flex items-center justify-between gap-4">
                <span className="text-xs text-muted">00:00:00.000</span>
                <div className="flex-1 h-0.5 bg-primary/20 rounded" />
                <span className="text-xs text-muted">00:00:00.500</span>
              </div>
              <div className="flex items-center justify-between mt-2 text-xs text-muted">
                <span>Playback Speed:</span>
                <span className="font-mono">1.0x</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Key Metrics */}
        <Card title="Key Temporal Metrics">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-4">
              <KV label="Mean Detection Age" value="140ms" sub="+40ms over budget" />
              <KV label="95th Percentile Latency" value="182ms" sub="+82ms over budget" />
              <KV label="Control Loop Jitter" value="28ms" sub="Nominal: <15ms" />
              <KV label="Safety Event Lag" value="92ms" sub="Within tolerance" />
            </div>

            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 bg-danger/20 rounded-full border border-danger/50" />
                <div className="space-y-1">
                  <p className="font-medium text-muted">Timeline Confidence</p>
                  <p className="text-sm font-mono text-danger">68%</p>
                </div>
              </div>
              <div className="w-full bg-primary/10 rounded-full h-2.5 overflow-hidden">
                <div className="bg-danger h-full w-[68%] transition-all duration-500" role="progressbar" aria-valuenow={68} aria-valuemin={0} aria-valuemax={100} />
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Footer Actions */}
      <div className="mt-12 pt-8 border-t border-white/10">
        <div className="flex flex-wrap justify-end gap-4">
          <Button variant="outline" onClick={() => alert("Export timeline")}>
            Export Timeline (JSON)
          </Button>
          <Button variant="primary" onClick={() => alert("Run temporal analysis")}>
            Run Temporal Analysis
          </Button>
        </div>
      </div>
    </div>
  );
}