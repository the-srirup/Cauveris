"use client";

import { Loader2, Zap, Clock, Eye, GitBranch, FlaskConical, Wrench, Database, FileText } from "lucide-react";

interface LazyPageLoaderProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
}

export function LazyPageLoader({ icon, title, description }: LazyPageLoaderProps) {
  return (
    <div className="min-h-screen bg-[var(--theme-background)] text-foreground flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center space-y-6">
        {icon && (
          <div className="w-16 h-16 mx-auto bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20 rounded-2xl flex items-center justify-center animate-pulse">
            <span className="text-[var(--color-accent)] text-2xl">{icon}</span>
          </div>
        )}
        <div className="space-y-3">
          <div className="flex items-center justify-center gap-2">
            <Loader2 className="h-5 w-5 text-[var(--color-accent)] animate-spin" />
            <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">{title}</h2>
          </div>
          {description && (
            <p className="text-[var(--color-text-muted)] text-sm">{description}</p>
          )}
        </div>
        <div className="flex items-center justify-center gap-3 text-xs text-[var(--color-text-muted)]">
          <span className="flex items-center gap-1">
            <Zap className="h-3 w-3" />
            Optimizing bundle
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Lazy loading
          </span>
        </div>
      </div>
    </div>
  );
}

export const CausalConstellationLoader = () => (
  <LazyPageLoader
    icon="🕸️"
    title="Causal Constellation"
    description="Loading causal graph visualization..."
  />
);

export const RealityRewindLoader = () => (
  <LazyPageLoader
    icon="⏮️"
    title="Reality Rewind"
    description="Loading temporal timeline..."
  />
);

export const HolographicReconstructionLoader = () => (
  <LazyPageLoader
    icon="🌌"
    title="Holographic Reconstruction"
    description="Loading 3D reconstruction..."
  />
);

export const GhostLabLoader = () => (
  <LazyPageLoader
    icon="👻"
    title="Ghost Lab"
    description="Loading experiment branches..."
  />
);

export const PatchForgeLoader = () => (
  <LazyPageLoader
    icon="🔧"
    title="Patch Forge"
    description="Loading patch candidates..."
  />
);

export const VictoryReplayLoader = () => (
  <LazyPageLoader
    icon="✅"
    title="Victory Replay"
    description="Loading validation results..."
  />
);

export const EvidenceVaultLoader = () => (
  <LazyPageLoader
    icon="📦"
    title="Evidence Vault"
    description="Loading artifact inventory..."
  />
);