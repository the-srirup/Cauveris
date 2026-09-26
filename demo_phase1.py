#!/usr/bin/env python
"""Phase 1 Demo: Holographic Evidence Reconstruction"""
from cauveris.holographic import *
import numpy as np

print('=== HOLOGRAPHIC EVIDENCE RECONSTRUCTION - PHASE 1 DEMO ===')
print()

# Realistic incident scenario: navigation service degradation after deployment
timeline = [
    {
        'event_id': 'deploy_1',
        'timestamp_ns': 100_000_000,
        'source_type': 'deployment_json',
        'source': 'deploy.json',
        'message': 'Deployment v42 rolled out to navigation_service (nav-controller v42)',
        'attributes': {'service': 'navigation_service', 'version': 'v42', 'component': 'navigation_controller'},
        'status': 'ok',
    },
    {
        'event_id': 'trace_1',
        'timestamp_ns': 150_000_000,
        'source_type': 'otel_trace',
        'source': 'traces',
        'message': 'Span for /nav/plan request',
        'attributes': {'service.name': 'navigation_controller', 'peer.service': 'planning_service', 'trace_id': 'abc123', 'duration_ns': 50_000_000, 'span.kind': 'SERVER'},
        'status': 'ok',
    },
    {
        'event_id': 'metric_1',
        'timestamp_ns': 200_000_000,
        'source_type': 'csv_metrics',
        'source': 'prometheus',
        'message': 'CPU utilization spike',
        'attributes': {'service': 'navigation_controller', 'instance': 'nav-1', 'cpu_usage': 0.92, 'memory_usage': 0.65},
        'status': 'warning',
    },
    {
        'event_id': 'log_1',
        'timestamp_ns': 250_000_000,
        'source_type': 'jsonl_log',
        'source': 'nav-controller.log',
        'message': 'ERROR: Path planning timeout after 5s',
        'attributes': {'service': 'navigation_controller', 'instance': 'nav-1', 'level': 'ERROR', 'error': 'timeout'},
        'status': 'error',
    },
    {
        'event_id': 'trace_2',
        'timestamp_ns': 300_000_000,
        'source_type': 'otel_trace',
        'source': 'traces',
        'message': 'Span for /plan/compute call to planning_service',
        'attributes': {'service.name': 'navigation_controller', 'peer.service': 'planning_service', 'trace_id': 'def456', 'duration_ns': 450000000, 'span.kind': 'CLIENT'},
        'status': 'error',
    },
    {
        'event_id': 'log_2',
        'timestamp_ns': 350_000_000,
        'source_type': 'jsonl_log',
        'source': 'planning_service.log',
        'message': 'WARN: High latency in motion planning',
        'attributes': {'service': 'planning_service', 'instance': 'plan-1', 'level': 'WARN', 'latency_ms': 450},
        'status': 'warning',
    },
    {
        'event_id': 'operator_1',
        'timestamp_ns': 400_000_000,
        'source_type': 'operator_note',
        'source': 'incident_log',
        'message': 'Scaling up navigation_controller replicas from 3 to 10',
        'attributes': {'service': 'navigation_controller'},
        'status': 'ok',
    },
]

incident_duration = 500_000_000

print('1. CONVERTING TIMELINE TO HOLOGRAPHIC EVIDENCE UNITS (HEUs)')
print('   Incident: Navigation service degradation post-deployment v42')
print(f'   Duration: 500ms, Events: {len(timeline)}')
print()

heus = convert_timeline_to_heus(timeline, {}, incident_duration)
print(f'   Generated {len(heus)} HEUs across {len(set(h.boundary_layer for h in heus))} boundary layers')
print()
for heu in heus:
    print(f'   {heu.boundary_layer.value:25s} | {heu.source_component:22s} | dims={list(heu.encoded_dimensions.keys())} | weight={heu.reconstruction_weight:.2f}')

print()
print('2. BUILDING SYSTEM TOPOLOGY FROM TIMELINE')
print()
topology = build_topology_from_timeline(timeline)
print(f'   Components: {len(topology.components)}')
for name, comp in topology.components.items():
    print(f'     - {name}: instances={comp.instance_ids}, layers={comp.boundary_layers}')
print(f'   Causal Edges: {len(topology.causal_edges)}')
for edge in topology.causal_edges:
    print(f'     - {edge.source} -> {edge.target} ({edge.edge_type}, {edge.latency_ms}ms, conf={edge.confidence})')

print()
print('3. CREATING HOLOGRAPHIC RECONSTRUCTION')
print()
recon = HolographicReconstruction(
    incident_id='NAV-DEG-2026-0042',
    reconstruction_timestamp_ns=1_000_000_000,
    time_window_ns=(0, incident_duration),
    overall_fidelity=0.87,
)

# Simulate reconstruction results based on HEUs
recon.reconstructed_services['navigation_controller_nav-1'] = ReconstructedServiceState(
    component_name='navigation_controller',
    instance_id='nav-1',
    cpu_usage=0.92,
    memory_usage=0.65,
    network_usage=0.2,
    error_rate=0.15,
    confidence=0.85,
    coverage=0.78,
    upstream_health={'planning_service': 0.6},
)

recon.reconstructed_services['planning_service_plan-1'] = ReconstructedServiceState(
    component_name='planning_service',
    instance_id='plan-1',
    cpu_usage=0.75,
    memory_usage=0.55,
    network_usage=0.15,
    error_rate=0.0,
    confidence=0.7,
    coverage=0.65,
)

# Add network reconstruction
recon.reconstructed_network.add_edge('navigation_controller', 'planning_service', NetworkEdge(
    source='navigation_controller',
    target='planning_service',
    latency_ms=450.0,
    loss_rate=0.0,
    confidence=0.8,
))
recon.reconstructed_network.add_edge('planning_service', 'localization_service', NetworkEdge(
    source='planning_service',
    target='localization_service',
    latency_ms=8.0,
    loss_rate=0.0,
    confidence=0.6,
))

# Add resource reconstruction
recon.reconstructed_resources = ReconstructedResourceState(
    total_cpu_cores=32.0,
    total_memory_gb=64.0,
    used_cpu_cores=22.0,
    used_memory_gb=38.0,
    cpu_by_component={'navigation_controller': 12.0, 'planning_service': 6.0},
    memory_by_component={'navigation_controller': 18.0, 'planning_service': 12.0},
)

# Add ambiguity region
recon.ambiguity_regions.append(AmbiguityRegion(
    component='navigation_controller',
    time_range_ns=(100_000_000, 500_000_000),
    affected_dimensions=['cpu_pressure', 'network_latency'],
    ambiguity_score=0.35,
    missing_layers=['network_flow'],
    description='No network flow data to validate cross-service latency attribution',
))

print(f'   Incident ID: {recon.incident_id}')
print(f'   Fidelity: {recon.overall_fidelity:.0%}')
print(f'   Reconstructed Services: {len(recon.reconstructed_services)}')
print()
print('   SERVICE HEALTH ANALYSIS:')
for name, svc in recon.reconstructed_services.items():
    health = 'HEALTHY' if svc.is_healthy else 'UNHEALTHY'
    print(f'     {svc.component_name}/{svc.instance_id}: {health}')
    print(f'       CPU: {svc.cpu_usage:.0%}, Mem: {svc.memory_usage:.0%}, Net: {svc.network_usage:.0%}, Err: {svc.error_rate:.0%}')
    print(f'       Confidence: {svc.confidence:.0%}, Coverage: {svc.coverage:.0%}')
    print(f'       Bottleneck: {svc.primary_bottleneck or "none"}')
    if svc.upstream_health:
        print(f'       Upstream health: {svc.upstream_health}')

print()
print('   NETWORK TOPOLOGY:')
for edge_key, edge in recon.reconstructed_network.edges.items():
    print(f'     {edge.source} -> {edge.target}: {edge.latency_ms:.1f}ms, loss={edge.loss_rate:.0%}, conf={edge.confidence:.0%}')

print()
print('   RESOURCE UTILIZATION:')
print(f'     CPU: {recon.reconstructed_resources.cpu_utilization:.0%} ({recon.reconstructed_resources.used_cpu_cores:.0f}/{recon.reconstructed_resources.total_cpu_cores:.0f} cores)')
print(f'     Memory: {recon.reconstructed_resources.memory_utilization:.0%} ({recon.reconstructed_resources.used_memory_gb:.0f}/{recon.reconstructed_resources.total_memory_gb:.0f} GB)')

print()
print('   AMBIGUITY REGIONS:')
for region in recon.ambiguity_regions:
    start_ms = region.time_range_ns[0] / 1e6
    end_ms = region.time_range_ns[1] / 1e6
    print(f'     {region.component} [{start_ms:.0f}-{end_ms:.0f}ms]: {region.description}')
    print(f'       Score: {region.ambiguity_score:.0%}, Missing: {region.missing_layers}')

print()
print(f'   HIGH AMBIGUITY ALERT: {"YES" if recon.has_high_ambiguity else "NO"}')
print()
print('=== PHASE 1 COMPLETE - Ready for Phase 2: Reconstruction Engine Core ===')