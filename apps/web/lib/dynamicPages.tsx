"use client";

import dynamic from "next/dynamic";
import { CausalConstellationLoader, RealityRewindLoader, HolographicReconstructionLoader, GhostLabLoader, PatchForgeLoader, VictoryReplayLoader, EvidenceVaultLoader } from "@/components/LazyPageLoader";

// Heavy pages - loaded dynamically to reduce initial bundle size
export const CausalConstellationPage = dynamic(() => import("@/app/causal-constellation/page").then((mod) => mod.default ?? mod), {
  loading: () => <CausalConstellationLoader />,
  ssr: false,
});

export const RealityRewindPage = dynamic(() => import("@/app/reality-rewind/page").then((mod) => mod.default ?? mod), {
  loading: () => <RealityRewindLoader />,
  ssr: false,
});

export const HolographicReconstructionPage = dynamic(() => import("@/app/holographic-reconstruction/page").then((mod) => mod.default ?? mod), {
  loading: () => <HolographicReconstructionLoader />,
  ssr: false,
});

export const GhostLabPage = dynamic(() => import("@/app/ghost-lab/page").then((mod) => mod.default ?? mod), {
  loading: () => <GhostLabLoader />,
  ssr: false,
});

export const PatchForgePage = dynamic(() => import("@/app/patch-forge/page").then((mod) => mod.default ?? mod), {
  loading: () => <PatchForgeLoader />,
  ssr: false,
});

export const VictoryReplayPage = dynamic(() => import("@/app/victory-replay/page").then((mod) => mod.default ?? mod), {
  loading: () => <VictoryReplayLoader />,
  ssr: false,
});

export const EvidenceVaultPage = dynamic(() => import("@/app/evidence-vault/page").then((mod) => mod.default ?? mod), {
  loading: () => <EvidenceVaultLoader />,
  ssr: false,
});

// Light pages - eager load
export { default as MissionControlPage } from "@/app/page";
export { default as SettingsPage } from "@/app/settings/page";
export { default as ReportsPage } from "@/app/reports/page";