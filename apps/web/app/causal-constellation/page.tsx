"use client";

import { Button, Card, Badge, PageHeader } from "@/components/ui";

export default function CausalConstellation() {
  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      {/* Header */}
      <PageHeader
        title="Causal Constellation"
        subtitle="Multi-dimensional hypothesis mapping and evidence linkage"
        badge={<Badge tone="primary">4 Active Hypotheses</Badge>}
      />

      {/* Main Content */}
      <div className="grid gap-8 lg:grid-cols-[300px_1fr]">
        {/* Left: Hypothesis Cards */}
        <Card title="Root-Cause Hypotheses">
          <div className="space-y-6">
            {/* Hypothesis H1 */}
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <div className="w-3 h-3 bg-primary/20 rounded-full border border-primary/50 flex-shrink-0 mt-1" />
                <div className="flex-1 space-y-2">
                  <div className="flex justify-between items-start">
                    <h3 className="font-semibold text-primary">H1: Batching Window Increase</h3>
                    <Badge tone="primary">INFERRED</Badge>
                  </div>
                  <p className="text-sm text-muted">
                    Increased dynamic batching window in deployment v42 caused inference P99 latency to exceed robot freshness budget.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge tone="secondary">Supporting: 2</Badge>
                    <Badge tone="danger">Contradicting: 0</Badge>
                    <Badge tone="muted">Missing: 1</Badge>
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <span className="text-xs text-muted">Confidence:</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-primary">75%</span>
                      <div className="w-24 h-1.5 bg-primary/10 rounded-full overflow-hidden">
                        <div className="bg-primary h-full w-3/4 transition-all duration-500" role="progressbar" aria-valuenow={75} aria-valuemin={0} aria-valuemax={100} />
                      </div>
                    </div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => alert("Test H1")} className="mt-2 w-full">
                    Test Hypothesis
                  </Button>
                </div>
              </div>
            </div>

            {/* Hypothesis H2 */}
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <div className="w-3 h-3 bg-primary/20 rounded-full border border-primary/50 flex-shrink-0 mt-1" />
                <div className="flex-1 space-y-2">
                  <div className="flex justify-between items-start">
                    <h3 className="font-semibold text-primary">H2: QoS Retention</h3>
                    <Badge tone="primary">INFERRED</Badge>
                  </div>
                  <p className="text-sm text-muted">
                    ROS 2 QoS retains older detection messages causing stale-data consumption.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge tone="secondary">Supporting: 1</Badge>
                    <Badge tone="danger">Contradicting: 1</Badge>
                    <Badge tone="muted">Missing: 0</Badge>
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <span className="text-xs text-muted">Confidence:</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-primary">45%</span>
                      <div className="w-24 h-1.5 bg-primary/10 rounded-full overflow-hidden">
                        <div className="bg-primary h-full w-[45%] transition-all duration-500" role="progressbar" aria-valuenow={45} aria-valuemin={0} aria-valuemax={100} />
                      </div>
                    </div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => alert("Test H2")} className="mt-2 w-full">
                    Test Hypothesis
                  </Button>
                </div>
              </div>
            </div>

            {/* Hypothesis H3 */}
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <div className="w-3 h-3 bg-primary/20 rounded-full border border-primary/50 flex-shrink-0 mt-1" />
                <div className="flex-1 space-y-2">
                  <div className="flex justify-between items-start">
                    <h3 className="font-semibold text-primary">H3: Clock Skew</h3>
                    <Badge tone="primary">INFERRED</Badge>
                  </div>
                  <p className="text-sm text-muted">
                    Clock skew between service host and robot makes fresh detections appear stale.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge tone="secondary">Supporting: 0</Badge>
                    <Badge tone="danger">Contradicting: 2</Badge>
                    <Badge tone="muted">Missing: 0</Badge>
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <span className="text-xs text-muted">Confidence:</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-primary">20%</span>
                      <div className="w-24 h-1.5 bg-primary/10 rounded-full overflow-hidden">
                        <div className="bg-primary h-full w-1/5 transition-all duration-500" role="progressbar" aria-valuenow={20} aria-valuemin={0} aria-valuemax={100} />
                      </div>
                    </div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => alert("Test H3")} className="mt-2 w-full">
                    Test Hypothesis
                  </Button>
                </div>
              </div>
            </div>

            {/* Hypothesis H4 */}
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <div className="w-3 h-3 bg-primary/20 rounded-full border border-primary/50 flex-shrink-0 mt-1" />
                <div className="flex-1 space-y-2">
                  <div className="flex justify-between items-start">
                    <h3 className="font-semibold text-primary">H4: GPU Load/Throttling</h3>
                    <Badge tone="primary">INFERRED</Badge>
                  </div>
                  <p className="text-sm text-muted">
                    GPU load or throttling causes latency spike independent of deployment v42.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge tone="secondary">Supporting: 1</Badge>
                    <Badge tone="danger">Contradicting: 1</Badge>
                    <Badge tone="muted">Missing: 0</Badge>
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <span className="text-xs text-muted">Confidence:</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-primary">30%</span>
                      <div className="w-24 h-1.5 bg-primary/10 rounded-full overflow-hidden">
                        <div className="bg-primary h-full w-[30%] transition-all duration-500" role="progressbar" aria-valuenow={30} aria-valuemin={0} aria-valuemax={100} />
                      </div>
                    </div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => alert("Test H4")} className="mt-2 w-full">
                    Test Hypothesis
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </Card>

        {/* Right: Evidence Graph */}
        <Card title="Evidence Event Graph">
          <div className="aspect-video w-full bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative">
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="space-y-4 text-center">
                <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center mb-4 ring-2 ring-primary/20 mx-auto" />
                <p className="text-lg font-medium text-white">
                  Interactive causal graph
                </p>
                <p className="text-sm text-muted max-w-md mx-auto">
                  Showing links between deployment, configuration, GPU queue, trace spans, ROS messages, source code, controller events, and safety stops.
                </p>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}