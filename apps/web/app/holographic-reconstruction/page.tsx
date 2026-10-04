"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { PageHeader, Card, Badge, Button, Divider } from "@/components/ui";
import { Zap, Eye, GitBranch, FlaskConical, Wrench, RotateCcw, Database, FileText, Settings, ArrowRight, AlertTriangle, CheckCircle, Loader2, ExternalLink, Clock } from "lucide-react";
import { tv } from "tailwind-variants";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell, buildIncidentContext } from "@/lib/useShell";
import { useEffect } from "react";
import { useAuthStore } from "@/lib/auth";

const cardStyles = tv({
  base: `
    glass ring-glow rounded-2xl border border-[var(--color-border)] p-[var(--card-padding)]
    transition-all duration-200 hover:border-[var(--color-brand-primary)]/30 hover:shadow-lg hover:shadow-[var(--color-brand-primary)]/10
    group cursor-pointer
  `,
});

export default function HolographicReconstructionPage() {
  const { incidentId, judgeMode, engineerMode } = useActiveIncident();
  const { setIncidentContext } = useShell();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const router = useRouter();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?redirect=/holographic-reconstruction');
    }
  }, [isAuthenticated, authLoading, router]);

  // Show loading while auth is initializing
  if (authLoading) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-primary">
          <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">Loading Holographic Reconstruction...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-primary">
          <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">Redirecting to login...</p>
      </div>
    );
  }

  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Holographic Reconstruction",
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

  const features = [
    {
      icon: Zap,
      title: "3D Causal Reconstruction",
      description: "Interactive 3D visualization of the causal graph with spatial layout algorithms",
      status: "planned",
      href: "#",
    },
    {
      icon: Eye,
      title: "Multi-Perspective Views",
      description: "Switch between topological, temporal, and spatial representations of causality",
      status: "planned",
      href: "#",
    },
    {
      icon: GitBranch,
      title: "Counterfactual Simulation",
      description: "Simulate alternative execution paths by modifying node states in real-time",
      status: "planned",
      href: "#",
    },
    {
      icon: FlaskConical,
      title: "Ghost Trajectory Overlay",
      description: "Overlay simulated ghost trajectories on the reconstruction for comparison",
      status: "planned",
      href: "#",
    },
    {
      icon: Wrench,
      title: "Patch Visualization",
      description: "Visualize proposed patches as structural modifications to the causal graph",
      status: "planned",
      href: "#",
    },
    {
      icon: RotateCcw,
      title: "Replay & Rollback",
      description: "Step through reconstruction states with full temporal navigation",
      status: "planned",
      href: "#",
    },
  ];

  const navigationCards = [
    {
      icon: Clock,
      title: "Reality Rewind",
      description: "Event timeline & temporal navigation",
      href: "/reality-rewind",
      badge: "live",
    },
    {
      icon: GitBranch,
      title: "Causal Constellation",
      description: "Interactive causal graph explorer",
      href: "/causal-constellation",
      badge: "live",
    },
    {
      icon: FlaskConical,
      title: "Ghost Lab",
      description: "Counterfactual experiments & simulation",
      href: "/ghost-lab",
      badge: "live",
    },
    {
      icon: Wrench,
      title: "Patch Forge",
      description: "Patch candidates & verification",
      href: "/patch-forge",
      badge: "live",
    },
    {
      icon: RotateCcw,
      title: "Victory Replay",
      description: "Before/after comparison & rollback",
      href: "/victory-replay",
      badge: "live",
    },
    {
      icon: Database,
      title: "Evidence Vault",
      description: "Artifact inventory & provenance",
      href: "/evidence-vault",
      badge: "live",
    },
  ];

  return (
    <div className="flex flex-col gap-[var(--section-gap)]">
      <PageHeader
        title="Holographic Reconstruction"
        subtitle="Immersive 3D causal analysis — Coming Soon"
        badge={<Badge tone="amber" dot>Planned</Badge>}
      />

      <div className="grid gap-[var(--section-gap)] md:grid-cols-2 lg:grid-cols-3">
        {features.map((feature, index) => (
          <Link key={index} href={feature.href} className={cardStyles()}>
            <div className="flex items-start gap-[var(--space-4)]">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[var(--color-brand-primary)]/10 text-[var(--color-brand-primary)] group-hover:bg-[var(--color-brand-primary)]/20 transition-colors">
                <feature.icon className="h-6 w-6" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-[var(--color-text-primary)] group-hover:text-[var(--color-brand-primary)] transition-colors">{feature.title}</h3>
                <p className="mt-[var(--space-1)] text-sm text-[var(--color-text-muted)] line-clamp-2">{feature.description}</p>
                <div className="mt-[var(--space-3)] flex items-center gap-[var(--space-2)]">
                  <Badge tone={feature.status === "live" ? "success" : "amber"} dot className="text-[10px]">
                    {feature.status === "live" ? "Live" : "Planned"}
                  </Badge>
                  <span className="text-[11px] text-[var(--color-text-muted)]/70">Phase {index + 1}</span>
                </div>
              </div>
            </div>
            <div className="mt-[var(--space-4)] flex items-center justify-end">
              <span className="text-[11px] text-[var(--color-text-muted)]/50 group-hover:text-[var(--color-brand-primary)] transition-colors flex items-center gap-[var(--space-1)]">
                Explore <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </div>
          </Link>
        ))}
      </div>

      <Divider className="my-[var(--divider-margin)]" />

      <section>
        <div className="flex items-center justify-between mb-[var(--space-6)]">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Related Investigation Tools</h2>
        </div>
        <div className="grid gap-[var(--space-4)] md:grid-cols-2 lg:grid-cols-3">
          {navigationCards.map((card, index) => (
            <Link key={index} href={card.href} className={cardStyles()}>
              <div className="flex items-start gap-[var(--space-4)]">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--color-brand-primary)]/10 text-[var(--color-brand-primary)]">
                  <card.icon className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-[var(--color-text-primary)]">{card.title}</h3>
                  <p className="mt-[var(--space-1)] text-sm text-[var(--color-text-muted)]">{card.description}</p>
                </div>
              </div>
              <div className="mt-[var(--space-4)] flex items-center justify-between">
                <Badge tone={card.badge === "live" ? "success" : "amber"} dot className="text-[10px]">
                  {card.badge === "live" ? "Available" : "Planned"}
                </Badge>
                <ArrowRight className="h-4 w-4 text-[var(--color-text-muted)]/50 group-hover:text-[var(--color-brand-primary)] transition-colors" />
              </div>
            </Link>
          ))}
        </div>
      </section>

      <Divider className="my-[var(--divider-margin)]" />

      <section>
        <div className="flex items-center justify-between mb-[var(--space-6)]">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Development Roadmap</h2>
        </div>
        <div className="space-y-[var(--space-4)]">
          {[
            { phase: "Phase 1", title: "Core 3D Engine", items: ["Three.js/React Three Fiber integration", "Spatial layout algorithms (force-directed, hierarchical)", "WebGL rendering pipeline with LOD"], status: "in-progress" },
            { phase: "Phase 2", title: "Interaction Layer", items: ["Node/edge selection & inspector integration", "Camera controls (orbit, pan, zoom, focus)", "Time slider for temporal navigation"], status: "planned" },
            { phase: "Phase 3", title: "Advanced Features", items: ["Counterfactual simulation engine", "Ghost trajectory overlay", "Patch visualization as graph mutations"], status: "planned" },
            { phase: "Phase 4", title: "Polish & Integration", items: ["Performance optimization for large graphs", "Export to GLTF/USDZ", "Collaborative annotation layer"], status: "planned" },
          ].map((phase, i) => (
            <Card key={i} tone={phase.status === "in-progress" ? "accent" : "default"}>
              <div className="flex items-start gap-[var(--space-4)]">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-brand-primary)]/10 text-[var(--color-brand-primary)]">
                  <span className="font-bold text-lg">{i + 1}</span>
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-[var(--space-2)] mb-[var(--space-2)]">
                    <span className="font-semibold text-[var(--color-text-primary)]">{phase.phase}</span>
                    <Badge tone={phase.status === "in-progress" ? "primary" : "muted"} className="text-[10px]">
                      {phase.status === "in-progress" ? "In Progress" : "Planned"}
                    </Badge>
                  </div>
                  <h3 className="font-medium text-[var(--color-text-primary)]">{phase.title}</h3>
                  <ul className="mt-[var(--space-2)] space-y-[var(--space-1)] text-sm text-[var(--color-text-muted)]">
                    {phase.items.map((item, j) => (
                      <li key={j} className="flex items-center gap-[var(--space-2)]">
                        <CheckCircle className="h-3.5 w-3.5 text-[var(--color-brand-primary)]/50 flex-shrink-0" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}