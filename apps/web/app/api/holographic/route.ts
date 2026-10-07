import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  try {

    const { searchParams } = new URL(request.url);
    const incidentId = searchParams.get("incidentId");

    if (!incidentId) {
      return NextResponse.json({ error: "incidentId required" }, { status: 400 });
    }

    // In production, fetch from Python backend via gRPC/REST
    // For now, return mock data
    const mockData = generateMockData(incidentId);

    return NextResponse.json({ data: mockData });
  } catch (error) {
    console.error("Holographic API error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

function generateMockData(incidentId: string) {
  const components = [
    { id: "api-gateway", name: "API Gateway", type: "gateway", pos: [0, 0, 0] as [number, number, number] },
    { id: "auth-service", name: "Auth Service", type: "service", pos: [-80, 50, 30] as [number, number, number] },
    { id: "user-db", name: "User Database", type: "database", pos: [80, 50, -30] as [number, number, number] },
    { id: "cache-layer", name: "Redis Cache", type: "cache", pos: [-40, -50, 60] as [number, number, number] },
    { id: "payment-svc", name: "Payment Service", type: "service", pos: [40, -50, -60] as [number, number, number] },
    { id: "notification-svc", name: "Notification Service", type: "service", pos: [100, 0, 40] as [number, number, number] },
    { id: "message-queue", name: "Message Queue", type: "message_queue", pos: [-80, -30, -40] as [number, number, number] },
    { id: "monitoring", name: "Monitoring", type: "monitoring", pos: [0, 80, 0] as [number, number, number] },
  ];

  const typeColors: Record<string, string> = {
    service: "#3b82f6",
    database: "#8b5cf6",
    cache: "#06b6d4",
    gateway: "#ec4899",
    message_queue: "#84cc16",
    monitoring: "#f59e0b",
  };

  const bulk_nodes = components.map((c, i) => {
    const health = 0.9 - i * 0.08;
    const cpu = 0.3 + Math.random() * 0.4;
    const mem = 0.4 + Math.random() * 0.3;
    return {
      id: c.id,
      name: c.name,
      type: c.type,
      position: c.pos,
      size: 8 + (cpu + mem) * 15,
      color: typeColors[c.type] || "#6b7280",
      health,
      metrics: {
        cpu_usage: cpu,
        memory_usage: mem,
        network_usage: Math.random() * 0.5,
        error_rate: Math.random() * 0.05,
        latency_p99_ms: 50 + Math.random() * 200,
      },
      confidence: 0.85 + Math.random() * 0.1,
      config_changed: Math.random() > 0.7,
    };
  });

  const edges = [
    { source: "api-gateway", target: "auth-service", latency: 5 },
    { source: "api-gateway", target: "user-db", latency: 12 },
    { source: "api-gateway", target: "cache-layer", latency: 3 },
    { source: "auth-service", target: "user-db", latency: 8 },
    { source: "auth-service", target: "cache-layer", latency: 2 },
    { source: "payment-svc", target: "message-queue", latency: 15 },
    { source: "notification-svc", target: "message-queue", latency: 10 },
    { source: "monitoring", target: "api-gateway", latency: 1 },
  ];

  const bulk_edges = edges.map(e => ({
    source: e.source,
    target: e.target,
    type: "causal" as const,
    thickness: 2 + Math.random() * 2,
    color: "#94a3b8",
    latency_ms: e.latency,
    source_health: 0.85,
    target_health: 0.8,
  }));

  const boundary_layers: Record<string, Record<string, any>> = {};
  components.forEach(c => {
    boundary_layers[c.id] = {
      application_log: {
        reconstruction_weight: 0.8 + Math.random() * 0.2,
        ambiguity_score: Math.random() * 0.3,
        color: "#10b981",
      },
      metrics_export: {
        reconstruction_weight: 0.6 + Math.random() * 0.3,
        ambiguity_score: Math.random() * 0.4,
        color: "#3b82f6",
      },
      distributed_trace: {
        reconstruction_weight: 0.9 + Math.random() * 0.1,
        ambiguity_score: Math.random() * 0.1,
        color: "#8b5cf6",
      },
    };
  });

  const ambiguity_regions = [
    {
      component: "payment-svc",
      dimension: "latency_p99_ms",
      affected_dimensions: ["latency_p99_ms", "error_rate"],
      time_range_ns: [1000000000, 5000000000] as [number, number],
      duration_ms: 4000,
      ambiguity_score: 0.65,
      missing_layers: ["metrics_export"],
      description: "Missing metrics during peak load window",
      severity: "high" as const,
    },
    {
      component: "cache-layer",
      dimension: "memory_usage",
      affected_dimensions: ["memory_usage"],
      time_range_ns: [2000000000, 6000000000] as [number, number],
      duration_ms: 4000,
      ambiguity_score: 0.35,
      missing_layers: ["infrastructure_log"],
      description: "Cache eviction events not captured",
      severity: "medium" as const,
    },
  ];

  return {
    incident_id: incidentId,
    bulk_nodes,
    bulk_edges,
    boundary_layers,
    scale_hierarchy: [
      { scale: "millisecond", time_window_ns: [0, 10000000], fidelity: 0.92, num_components: 8 },
      { scale: "second", time_window_ns: [0, 10000000000], fidelity: 0.87, num_components: 8 },
      { scale: "minute", time_window_ns: [0, 60000000000], fidelity: 0.75, num_components: 8 },
    ],
    ambiguity_regions,
    counterfactual: null,
    anomalies: [
      { component: "payment-svc", severity: "high", description: "Latency spike > 500ms", confidence: 0.9 },
      { component: "cache-layer", severity: "medium", description: "Memory pressure detected", confidence: 0.7 },
    ],
    metadata: {
      overall_fidelity: 0.87,
      boundary_residual: 0.12,
      num_components: 8,
      num_ambiguity_regions: 2,
      time_window_ns: 10000000000,
    },
  };
}