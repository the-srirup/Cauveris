"use client";

import dynamic from "next/dynamic";
import { CausalConstellationLoader, RealityRewindLoader, HolographicReconstructionLoader, GhostLabLoader, PatchForgeLoader, VictoryReplayLoader, EvidenceVaultLoader } from "@/components/LazyPageLoader";

// Heavy pages - loaded dynamically to reduce initial bundle size
export const CausalConstellationPage = dynamic(() => import("@/app/causal-constellation/page").then(mod => mod.default), {
  loading: () => <CausalConstellationLoader />,
  ssr: false,
});

export const RealityRewindPage = dynamic(() => import("@/app/reality-rewind/page").then(mod => mod.default), {
  loading: () => <RealityRewindLoader />,
  ssr: false,
});

export const HolographicReconstructionPage = dynamic(() => import("@/app/holographic-reconstruction/page").then(mod => mod.default), {
  loading: () => <HolographicReconstructionLoader />,
  ssr: false,
});

export const GhostLabPage = dynamic(() => import("@/app/ghost-lab/page").then(mod => mod.default), {
  loading: () => <GhostLabLoader />,
  ssr: false,
});

export const PatchForgePage = dynamic(() => import("@/app/patch-forge/page").then(mod => mod.default), {
  loading: () => <PatchForgeLoader />,
  ssr: false,
});

export const VictoryReplayPage = dynamic(() => import("@/app/victory-replay/page").then(mod => mod.default), {
  loading: () => <VictoryReplayLoader />,
  ssr: false,
});

export const EvidenceVaultPage = dynamic(() => import("@/app/evidence-vault/page").then(mod => mod.default), {
  loading: () => <EvidenceVaultLoader />,
  ssr: false,
});

// Light pages - eager load
export { default as MissionControlPage } from "@/app/page";
export { default as SettingsPage } from "@/app/settings/page";
export { default as ReportsPage } from "@/app/reports/page";