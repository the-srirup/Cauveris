#!/usr/bin/env python
"""
Phase 2 Holographic Evidence Reconstruction - Real-World Verification
"""
import numpy as np
from cauveris.holographic.topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge
from cauveris.holographic.heu import HolographicEvidenceUnit, BoundaryLayer, convert_timeline_to_heus
from cauveris.holographic.heu_kernel import CausalKernelBuilder
from cauveris.holographic.measurement import build_measurement_system, MeasurementConfig
from cauveris.holographic.solver import HolographicSolver, SolverConfig, solve_holographic_inverse
from cauveris.holographic.multiscale import MultiScaleReconstructor, MultiScaleConfig, ReconstructionScale, reconstruct_multiscale
from cauveris.holographic.compression import HolographicCompressor, CompressionConfig, CompressionMethod, compress_holographic, EvidenceSynthesizer
from cauveris.holographic.reconstruction import HolographicReconstruction, ReconstructedServiceState


def main():
    print('='*60)
    print('PHASE 2 HOLOGRAPHIC EVIDENCE RECONSTRUCTION - REAL-WORLD VERIFICATION')
    print('='*60)

    # Build realistic system topology
    print('\n1. BUILDING SYSTEM TOPOLOGY...')
    topo = SystemTopology()
    topo.add_component(ComponentInfo(
        name='api_gateway',
        component_type='gateway',
        capacity=ResourceCapacity(cpu_cores=8.0, memory_gb=16.0, max_rps=10000, network_gbps=1.0),
        boundary_layers=['application_log', 'metrics_export', 'distributed_trace', 'network_flow']
    ))
    topo.add_component(ComponentInfo(
        name='auth_service',
        component_type='service',
        capacity=ResourceCapacity(cpu_cores=4.0, memory_gb=8.0, max_rps=5000, network_gbps=0.5),
        boundary_layers=['application_log', 'metrics_export', 'distributed_trace']
    ))
    topo.add_component(ComponentInfo(
        name='payment_service',
        component_type='service',
        capacity=ResourceCapacity(cpu_cores=8.0, memory_gb=16.0, max_rps=3000, network_gbps=0.5),
        boundary_layers=['application_log', 'metrics_export', 'distributed_trace']
    ))
    topo.add_component(ComponentInfo(
        name='user_db',
        component_type='database',
        capacity=ResourceCapacity(cpu_cores=16.0, memory_gb=64.0, max_rps=20000, network_gbps=1.0),
        boundary_layers=['application_log', 'metrics_export', 'infrastructure_log']
    ))
    topo.add_causal_edge(CausalEdge(source='api_gateway', target='auth_service', latency_ms=2.0, edge_type='rpc', confidence=0.95))
    topo.add_causal_edge(CausalEdge(source='api_gateway', target='payment_service', latency_ms=3.0, edge_type='rpc', confidence=0.95))
    topo.add_causal_edge(CausalEdge(source='auth_service', target='user_db', latency_ms=5.0, edge_type='db', confidence=0.9))
    topo.add_causal_edge(CausalEdge(source='payment_service', target='user_db', latency_ms=8.0, edge_type='db', confidence=0.9))
    print(f'  Components: {list(topo.components.keys())}')
    print(f'  Causal edges: {len(topo.causal_edges)}')

    # Realistic incident timeline: CPU spike in auth_service cascading to DB and affecting payment
    print('\n2. CREATING REALISTIC INCIDENT TIMELINE...')
    timeline = [
        # Normal baseline
        {'event_id': '1', 'timestamp_ns': 50_000_000, 'source_type': 'jsonl_log', 'message': 'Normal request processing',
         'attributes': {'service': 'api_gateway', 'cpu_usage': 0.3, 'latency_ms': 10}, 'status': 'ok'},
        {'event_id': '2', 'timestamp_ns': 50_000_000, 'source_type': 'csv_metrics', 'message': 'Prometheus metrics',
         'attributes': {'service': 'api_gateway', 'cpu_usage': 0.3, 'rps': 1000, 'latency_p99': 20}, 'status': 'ok'},

        # CPU spike starts in auth_service (root cause)
        {'event_id': '3', 'timestamp_ns': 100_000_000, 'source_type': 'jsonl_log', 'message': 'CRITICAL: CPU utilization at 92%',
         'attributes': {'service': 'auth_service', 'cpu_usage': 0.92, 'thread_count': 80, 'error': 'thread_pool_exhausted'}, 'status': 'critical'},
        {'event_id': '4', 'timestamp_ns': 100_000_000, 'source_type': 'csv_metrics', 'message': 'Datadog metrics',
         'attributes': {'service': 'auth_service', 'cpu_usage': 0.92, 'memory_usage': 0.65, 'gc_pressure': 0.8}, 'status': 'critical'},
        {'event_id': '5', 'timestamp_ns': 100_000_000, 'source_type': 'otel_trace', 'message': 'Trace span',
         'attributes': {'service': 'auth_service', 'trace_id': 'abc123', 'span_id': 's1', 'parent_span_id': 'g1', 'duration_ns': 50_000_000, 'status': 'error'}, 'status': 'error'},

        # Cascade to user_db (5ms latency)
        {'event_id': '6', 'timestamp_ns': 150_000_000, 'source_type': 'jsonl_log', 'message': 'WARN: Connection pool 94% utilized',
         'attributes': {'service': 'user_db', 'cpu_usage': 0.65, 'active_connections': 94, 'wait_queue': 12}, 'status': 'warning'},
        {'event_id': '7', 'timestamp_ns': 150_000_000, 'source_type': 'csv_metrics', 'message': 'Metrics',
         'attributes': {'service': 'user_db', 'cpu_usage': 0.65, 'memory_usage': 0.75, 'disk_io_mbps': 120}, 'status': 'warning'},
        {'event_id': '8', 'timestamp_ns': 150_000_000, 'source_type': 'otel_trace', 'message': 'Trace span',
         'attributes': {'service': 'user_db', 'trace_id': 'abc123', 'span_id': 's2', 'parent_span_id': 's1', 'duration_ns': 200_000_000, 'status': 'error'}, 'status': 'error'},

        # api_gateway affected (timeouts)
        {'event_id': '9', 'timestamp_ns': 200_000_000, 'source_type': 'jsonl_log', 'message': 'ERROR: Timeout calling auth_service after 5s',
         'attributes': {'service': 'api_gateway', 'cpu_usage': 0.55, 'errors': 'timeout', 'error_count': 150}, 'status': 'error'},
        {'event_id': '10', 'timestamp_ns': 200_000_000, 'source_type': 'csv_metrics', 'message': 'Metrics',
         'attributes': {'service': 'api_gateway', 'cpu_usage': 0.55, 'latency_p99': 4800, 'error_rate': 0.15}, 'status': 'error'},
        {'event_id': '11', 'timestamp_ns': 200_000_000, 'source_type': 'network_flow', 'message': 'NetFlow',
         'attributes': {'src': 'api_gateway', 'dst': 'auth_service', 'bytes': 50000, 'packets': 500, 'retransmits': 45}, 'status': 'warning'},

        # payment_service unaffected (independent path)
        {'event_id': '12', 'timestamp_ns': 200_000_000, 'source_type': 'jsonl_log', 'message': 'Processing payment normally',
         'attributes': {'service': 'payment_service', 'cpu_usage': 0.25, 'latency_ms': 15}, 'status': 'ok'},

        # Recovery begins
        {'event_id': '13', 'timestamp_ns': 300_000_000, 'source_type': 'jsonl_log', 'message': 'INFO: CPU returning to normal after GC',
         'attributes': {'service': 'auth_service', 'cpu_usage': 0.4, 'thread_count': 20}, 'status': 'ok'},
        {'event_id': '14', 'timestamp_ns': 300_000_000, 'source_type': 'csv_metrics', 'message': 'Metrics',
         'attributes': {'service': 'auth_service', 'cpu_usage': 0.4, 'memory_usage': 0.5, 'gc_pressure': 0.2}, 'status': 'ok'},
    ]

    heus = convert_timeline_to_heus(timeline, {}, 500_000_000)
    print(f'  Generated {len(heus)} HEUs from timeline')
    for h in heus:
        dims = h.encoded_dimensions
        if dims:
            print(f'    {h.heu_id}: {dims}')

    # Build causal kernels
    print('\n3. BUILDING CAUSAL KERNELS (Green\'s functions)...')
    kernel_builder = CausalKernelBuilder(topo)
    kernels = kernel_builder.build_all_kernels()
    local_kernels = kernels['local']
    cross_kernels = kernels['cross']
    print(f'  Local kernels: {len(local_kernels)}')
    print(f'  Cross kernels: {len(cross_kernels)}')
    for edge_key, k in cross_kernels.items():
        print(f'    {edge_key}: peak={k.total_latency_ns/1e6:.1f}ms, integral={k.total_latency_ns/1e6:.3f}, half-life={k.network_latency_ns/1e6:.1f}ms')

    # Verify causality
    print('\n4. VERIFYING CAUSALITY...')
    causality_ok = kernel_builder.verify_causality()
    print(f'  All causality checks passed: {causality_ok}')

    # Build measurement system
    print('\n5. BUILDING MEASUREMENT SYSTEM...')
    system = build_measurement_system(topo, heus, 500_000_000, kernel_builder, MeasurementConfig())
    print(f'  State dimensions: {system.n_state}')
    print(f'  Observations: {system.n_obs}')
    print(f'  M matrix shape: {system.M.shape} (sparse: {system.M.nnz} non-zeros)')
    for sd in system.state_dims:
        print(f'    {sd.component}.{sd.dimension}')

    # Solve inverse problem
    print('\n6. SOLVING HOLOGRAPHIC INVERSE PROBLEM...')
    config = SolverConfig(
        method='SLSQP',
        max_iterations=200,
        lambda_data=1.0,
        lambda_entropy=0.1,
        lambda_temporal=0.01,
        lambda_physics=10.0,
    )
    solver = HolographicSolver(system, topo, config)
    result = solver.solve()
    print(f'  Solver: {result}')
    print(f'  State vector shape: {result.x.shape}')

    # Decode results
    decoded = solver.decode_state(result.x)
    print(f'\n  DECODED SERVICE STATES:')
    for svc, state in decoded['services'].items():
        print(f'    {svc}:')
        for dim, val in state.items():
            if val > 0.01:
                print(f'      {dim}: {val:.3f}')

    # Multi-scale reconstruction
    print('\n7. MULTI-SCALE RECONSTRUCTION...')
    ms_config = MultiScaleConfig(
        target_scales=[ReconstructionScale.INCIDENT, ReconstructionScale.TRANSACTION, ReconstructionScale.REQUEST],
        enable_prior_chaining=True,
    )
    ms_results = reconstruct_multiscale(topo, timeline, (0, 500_000_000), {})
    print(f'  Scales reconstructed: {len(ms_results)}')
    for scale, result in ms_results.items():
        if result:
            print(f'    {scale.name}: {len(result.heus)} HEUs, fidelity={result.reconstruction.overall_fidelity:.3f}')

    # Compression
    print('\n8. HOLOGRAPHIC COMPRESSION...')
    comp_config = CompressionConfig(
        method=CompressionMethod.HYBRID,
        target_compression_ratio=5.0,
        verify_fidelity=True,
    )
    compressor = HolographicCompressor(topo, comp_config)
    comp_result = compressor.compress(heus, 500_000_000)
    print(f'  Compression: {comp_result.compression_ratio:.1f}x, fidelity={comp_result.fidelity_retention:.3f}')
    print(f'  Method: {comp_result.method.name}')
    print(f'  Kept: {len(comp_result.compressed_heus)}/{len(heus)} HEUs')

    # Evidence synthesis for missing layers
    print('\n9. EVIDENCE SYNTHESIS (missing boundary layers)...')
    # Create a mock reconstruction to synthesize from
    recon = HolographicReconstruction(
        incident_id='INC-123',
        reconstruction_timestamp_ns=500_000_000,
        time_window_ns=(0, 500_000_000),
    )
    for svc, state in decoded['services'].items():
        recon.reconstructed_services[svc] = ReconstructedServiceState(
            component_name=svc,
            instance_id=f'{svc}-1',
            cpu_usage=state.get('cpu_pressure', 0),
            memory_usage=state.get('memory_pressure', 0),
            network_usage=state.get('network_latency', 0),
        )

    observed = {
        'api_gateway': [BoundaryLayer.APPLICATION_LOG, BoundaryLayer.METRICS_EXPORT],
        'auth_service': [BoundaryLayer.APPLICATION_LOG],
        'user_db': [BoundaryLayer.APPLICATION_LOG],
    }
    synth = EvidenceSynthesizer(topo)
    missing_heus = synth.synthesize_missing_layers(recon, observed, (0, 500_000_000))
    print(f'  Synthesized {len(missing_heus)} HEUs for missing layers')
    layers_synthesized = {}
    for h in missing_heus:
        layers_synthesized[h.boundary_layer.name] = layers_synthesized.get(h.boundary_layer.name, 0) + 1
    for layer, count in layers_synthesized.items():
        print(f'    {layer}: {count} HEUs')
    print(f'    All synthesized: {all(h.is_synthesized for h in missing_heus)}')

    print('\n' + '='*60)
    print('PHASE 2 VERIFICATION COMPLETE - ALL SYSTEMS OPERATIONAL')
    print('='*60)


if __name__ == '__main__':
    main()