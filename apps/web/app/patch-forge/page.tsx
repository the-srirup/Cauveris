"use client";

import { Button } from '@/components/ui';
import { Card, Stat, Badge, KV, PageHeader } from '@/components/ui';

export default function PatchForge() {
  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      {/* Header */}
      <PageHeader
        title="Patch Forge"
        subtitle="Candidate patch generation and rigorous verification"
        badge={<Badge tone="success">1 Verified Patch</Badge>}
      />

      {/* Main Content */}
      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        {/* Left: Patch Cards */}
        <Card title="Patch Candidates">
          <div className="space-y-6">
            {/* Patch Candidate 1 - Verified */}
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <div className="w-3 h-3 bg-success/20 rounded-full border border-success/50 flex-shrink-0 mt-1" />
                <div className="flex-1 space-y-3">
                  <div className="flex justify-between items-start">
                    <h3 className="font-semibold text-primary">PATCH-001</h3>
                    <Badge tone="success">VERIFIED</Badge>
                  </div>
                  <p className="text-sm font-mono text-muted mb-2">
                    --- a/src/inference/config.py
                    +++ b/src/inference/config.py
                    @@ -1 +1 @@
                    -BATCHING_WINDOW_MS = 200
                    +BATCHING_WINDOW_MS = 100
                  </p>
                  <div className="flex flex-wrap gap-2 mb-2">
                    <Badge tone="primary">-2 lines</Badge>
                    <Badge tone="primary">1 file</Badge>
                    <Badge tone="success">Score: 0.95</Badge>
                  </div>
                  <div className="mt-4">
                    <h4 className="text-sm font-semibold mb-2">Verification Results</h4>
                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Applies Cleanly:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Regression Test Fails Before:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Regression Test Passes After:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Original Failure Not Reproduced:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Existing Tests Pass:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Safety Invariants Pass:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Performance Within Budget:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Forbidden Change Scan Passes:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                      <div className="flex justify-between items-start">
                        <span className="text-muted">Rollback Test Passes:</span>
                        <span className="text-success font-mono">✓</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Patch Candidate 2 - Rejected */}
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <div className="w-3 h-3 bg-danger/20 rounded-full border border-danger/50 flex-shrink-0 mt-1" />
                <div className="flex-1 space-y-3">
                  <div className="flex justify-between items-start">
                    <h3 className="font-semibold text-primary">PATCH-002</h3>
                    <Badge tone="danger">REJECTED</Badge>
                  </div>
                  <p className="text-sm font-mono text-muted mb-2">
                    // This patch was rejected for weakening safety watchdog
                  </p>
                  <div className="flex flex-wrap gap-2 mb-2">
                    <Badge tone="primary">+5 lines</Badge>
                    <Badge tone="primary">1 file</Badge>
                    <Badge tone="danger">Score: 0.30</Badge>
                  </div>
                  <div className="mt-2">
                    <h4 className="text-sm font-semibold mb-2">Rejection Reason</h4>
                    <p className="text-danger text-sm">
                      Weakens safety watchdog by increasing timeout from 100ms to 200ms without justification
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Patch Candidate 3 - Rejected */}
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <div className="w-3 h-3 bg-danger/20 rounded-full border border-danger/50 flex-shrink-0 mt-1" />
                <div className="flex-1 space-y-3">
                  <div className="flex justify-between items-start">
                    <h3 className="font-semibold text-primary">PATCH-003</h3>
                    <Badge tone="danger">REJECTED</Badge>
                  </div>
                  <p className="text-sm font-mono text-muted mb-2">
                    // This patch was rejected for hard-coding the golden incident
                  </p>
                  <div className="flex flex-wrap gap-2 mb-2">
                    <Badge tone="primary">+10 lines</Badge>
                    <Badge tone="primary">2 files</Badge>
                    <Badge tone="danger">Score: 0.25</Badge>
                  </div>
                  <div className="mt-2">
                    <h4 className="text-sm font-semibold mb-2">Rejection Reason</h4>
                    <p className="text-danger text-sm">
                      Hard-codes deployment v41 check - not a general solution
                    </p>
                  </div>
                </div>
              </div>
            </div>
          }
        </Card>

        {/* Right: Controls & Stats */}
        <Card title="Verification Controls">
          <div className="space-y-6">
            {/* Verification Stats */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold mb-3 text-muted">Verification Summary</h3>
              <div className="grid grid-cols-2 gap-4">
                <Stat label="Total Candidates" value="3" sub="Generated" trend="flat" />
                <Stat label="Verified" value="1" sub="Passed all checks" trend="success" />
                <Stat label="Rejected" value="2" sub="Failed verification" trend="danger" />
                <Stat label="Success Rate" value="33%" sub="Verification rate" trend="warning" />
              </div>
            </div>

            {/* Action Buttons */}
            <div className="mt-6">
              <Button variant="outline" onClick={() => alert('Generate new candidates')} className="w-full mb-3">
                Generate New Candidates
              </Button>
              <Button variant="primary" onClick={() => alert('Create patch package')} className="w-full">
                Create Patch Package
              </Button>
            </div>
          }
        </Card>
      }
    </div>
  );
}