import { NextResponse } from "next/server";
import { api } from "@/lib/api";

/**
 * Health check endpoint for Next.js frontend
 * Returns basic service health status
 */
export async function GET(): Promise<NextResponse> {
  const startTime = Date.now();

  try {
    // Check if backend is reachable
    const health = await api.health();
    const latencyMs = Date.now() - startTime;

    return NextResponse.json({
      status: "healthy",
      service: "cauveris-web",
      version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",
      timestamp: new Date().toISOString(),
      latency_ms: latencyMs,
      backend: {
        status: health.status,
        latency_ms: health.latency_ms,
      },
    }, {
      status: 200,
      headers: {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Response-Time": `${latencyMs}ms`,
      },
    });
  } catch (error) {
    const latencyMs = Date.now() - startTime;

    return NextResponse.json({
      status: "unhealthy",
      service: "cauveris-web",
      version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",
      timestamp: new Date().toISOString(),
      latency_ms: latencyMs,
      error: error instanceof Error ? error.message : "Unknown error",
      backend: {
        status: "unreachable",
      },
    }, {
      status: 503,
      headers: {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Response-Time": `${latencyMs}ms`,
      },
    });
  }
}