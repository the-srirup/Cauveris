import { NextResponse } from "next/server";
import { api } from "@/lib/api";

/**
 * Readiness check endpoint for Next.js frontend
 * Returns detailed service readiness including all dependencies
 */
export async function GET(): Promise<NextResponse> {
  const startTime = Date.now();
  const checks: Record<string, { status: string; latency_ms?: number; error?: string }> = {};

  // Check backend API health
  try {
    const backendStart = Date.now();
    const health = await api.health();
    checks.backend_api = {
      status: health.status === "healthy" ? "ready" : "not_ready",
      latency_ms: Date.now() - backendStart,
    };
  } catch (error) {
    checks.backend_api = {
      status: "not_ready",
      error: error instanceof Error ? error.message : "Unknown error",
    };
  }

  // Check model provider health
  try {
    const modelStart = Date.now();
    const modelHealth = await api.modelHealth();
    checks.model_provider = {
      status: modelHealth.status === "healthy" ? "ready" : "degraded",
      latency_ms: Date.now() - modelStart,
    };
  } catch (error) {
    checks.model_provider = {
      status: "not_ready",
      error: error instanceof Error ? error.message : "Unknown error",
    };
  }

  // Check status center
  try {
    const statusStart = Date.now();
    const statusCenter = await api.getStatusCenter();
    checks.status_center = {
      status: statusCenter.status === "operational" ? "ready" : "degraded",
      latency_ms: Date.now() - statusStart,
    };
  } catch (error) {
    checks.status_center = {
      status: "not_ready",
      error: error instanceof Error ? error.message : "Unknown error",
    };
  }

  const totalLatencyMs = Date.now() - startTime;
  const allReady = Object.values(checks).every(check => check.status === "ready");

  return NextResponse.json({
    status: allReady ? "ready" : "not_ready",
    service: "cauveris-web",
    version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",
    timestamp: new Date().toISOString(),
    latency_ms: totalLatencyMs,
    checks,
  }, {
    status: allReady ? 200 : 503,
    headers: {
      "Cache-Control": "no-cache, no-store, must-revalidate",
      "X-Response-Time": `${totalLatencyMs}ms`,
    },
  });
}