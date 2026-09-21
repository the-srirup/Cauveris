"use client";

import { Button } from '@/components/ui';
import { Card, Stat, Badge, KV, PageHeader, Progress } from '@/components/ui';

export default function GhostLab() {
  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      {/* Header */}
      <PageHeader
        title="Ghost Lab"
        subtitle="Controlled experiment execution and counterfactual analysis"
        badge={<Badge tone="success">Experiment H1 Active</Badge>}
      />

      {/* Main Content */}
      <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
        {/* Left: Experiment Control & Visualization */}
        <div className="space-y-6">
          {/* Experiment Control */}
          <Card title="Experiment Control">
            <div className="space-y-4">
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
                <div>
                  <KV label="Active Branch" value="exp-h1 (H1)" sub="Selected" />
                </div>
                <div>
                  <Stat label="Trials Run" value="10" sub="/ 10 planned" trend="flat" />
                </div>
                <div>
                  <Stat label="Reproduction Rate" value="80%" sub="Trials with failure" trend="danger" />
                </div>
                <div>
                  <KV label="Failure Oracle" value="Safety stop triggered" sub="Emergency halt" />
                </div>
              }
            }
          </Card>

          {/* Parallel Trajectories */}
          <Card title="Parallel Robot Trajectories">
            <div className="aspect-video w-full bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative">
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="space-y-4 text-center">
                  <div className="w-24 h-24 bg-primary/10 rounded-full flex items-center justify-center mb-4 ring-2 ring-primary/20" />
                  <p className="text-lg font-medium text-white">
                    Counterfactual Simulation
                  </p>
                  <p className="text-sm text-muted">
                    10 parallel trajectories executing H1 intervention
                  </p>
                </div>
              }
            </div>
          </div>
        </div>

        {/* Right: Experiment Details & Outputs */}
        <div className="space-y-6">
          {/* Experiment Details */}
          <Card title="Experiment: H1 - Batching Window">
            <div className="space-y-4">
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-semibold text-primary">Intervention:</h3>
                <span className="font-mono text-primary">Reduce batching window from 200ms to 100ms</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-semibold text-muted">Status:</h3>
                <span className="font-mono text-success">REPRODUCED</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-semibold text-muted">Trials:</h3>
                <span className="font-mono text-primary">10</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-semibold text-muted">Reproductions:</h3>
                <span className="font-mono text-danger">8</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-semibold text-muted">Reproduction Rate:</h3>
                <span className="font-mono text-danger">80%</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-semibold text-muted">Conclusion:</h3>
                <span className="font-mono text-primary">Hypothesis supported</span>
              </div>
            </div>
          </Card>

          {/* Experiment Outputs */}
          <Card title="Experiment Outputs">
            <div className="space-y-4">
              <div className="flex justify-between items-start mb-2">
                <span className="text-sm font-medium text-muted">Logs Artifact:</span>
                <span className="font-mono text-muted">logs/exp-h1-system.log</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <span className="text-sm font-medium text-muted">Metrics Artifact:</span>
                <span className="font-mono text-muted">metrics/exp-h1-latency.csv</span>
              </div>
              <div className="flex justify-between items-start mb-2">
                <span className="text-sm font-medium text-muted">Replay Artifact:</span>
                <span className="font-mono text-muted">recordings/exp-h1-replay.mcap</span>
              </div>
            </div>
            <div className="mt-6">
              <h3 className="text-lg font-semibold mb-2">Key Metrics</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-start">
                  <span className="text-sm font-medium text-muted">Avg Latency:</span>
                  <span className="font-mono text-primary">95ms</span>
                </div>
                <div className="flex justify-between items-start">
                  <span className="text-sm font-medium text-muted">P99 Latency:</span>
                  <span className="font-mono text-success">105ms</span>
                </div>
                <div className="flex justify-between items-start">
                  <span className="text-sm font-medium text-muted">Control Loop P95:</span>
                  <span className="font-mono text-primary">45ms</span>
                </div>
                <div className="flex justify-between items-start">
                  <span className="text-sm font-medium text-muted">Safety Events:</span>
                  <span className="font-mono text-danger">2</span>
                </div>
              </div>
            </div>
          </Card>
        }
      </div>

      {/* Footer */}
      <footer className="mt-12 pt-8 border-t border-white/10">
        <div className="flex flex-wrap justify-end gap-4">
          <Button variant="outline" onClick={() => alert('Export experiment data')}>
            Export Experiment Data
          </Button>
          <Button variant="primary" onClick={() => alert('Run next experiment')}>
            Run Next Experiment
          </Button>
        </div>
      </footer>
    </div>
  );
}