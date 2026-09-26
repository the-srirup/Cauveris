"""
Holographic Compression Benchmarking.

Measures fidelity vs compression ratio curves for different compression methods.
"""

import numpy as np
import json
import time
from typing import Dict, List, Any
from dataclasses import dataclass, asdict

from cauveris.holographic.heu_kernel import CausalKernelBuilder
from cauveris.holographic.measurement import build_measurement_system, MeasurementConfig
from cauveris.holographic.solver import HolographicSolver, SolverConfig, SolverMethod
from cauveris.holographic.compression import (
    HolographicCompressor,
    CompressionConfig,
    CompressionMethod,
)
import sys
sys.path.insert(0, 'tests/holographic')
from synthetic import SyntheticIncidentGenerator, IncidentType


@dataclass
class CompressionBenchmarkResult:
    """Result of a single compression benchmark run."""
    incident_type: str
    method: str
    target_ratio: float
    achieved_ratio: float
    fidelity_retention: float
    num_heus_original: int
    num_heus_compressed: int
    solve_time_ms: float
    boundary_residual_original: float
    boundary_residual_compressed: float


def run_compression_benchmark(
    incident,
    method: CompressionMethod,
    target_ratios: List[float] = None,
) -> List[CompressionBenchmarkResult]:
    """Run compression benchmark for a single incident and method."""
    if target_ratios is None:
        target_ratios = [2.0, 5.0, 10.0, 20.0, 50.0, 100.0]

    # Build measurement system for original HEUs
    topology = incident.topology
    heus = incident.heus

    kernel_builder = CausalKernelBuilder(topology)
    kernel_builder.build_all_kernels()

    measurement_system = build_measurement_system(
        topology, heus, 60_000_000_000, kernel_builder, MeasurementConfig()
    )

    # Get original reconstruction
    config = SolverConfig(method=SolverMethod.SLSQP, max_iterations=100)
    solver = HolographicSolver(measurement_system, topology, config)
    start = time.time()
    original_result = solver.solve()
    original_solve_time = (time.time() - start) * 1000

    original_decode = solver.decode_state(original_result.x)

    results = []

    for ratio in target_ratios:
        comp_config = CompressionConfig(
            method=method,
            target_compression_ratio=ratio,
            verify_fidelity=True,
        )
        compressor = HolographicCompressor(topology, comp_config)

        comp_result = compressor.compress(heus, 60_000_000_000)

        if len(comp_result.compressed_heus) < 1:
            continue

        # Reconstruct from compressed HEUs
        comp_system = build_measurement_system(
            topology, comp_result.compressed_heus, 60_000_000_000, kernel_builder, MeasurementConfig()
        )
        comp_solver = HolographicSolver(comp_system, topology, config)
        comp_result_solve = comp_solver.solve()
        comp_decode = comp_solver.decode_state(comp_result_solve.x)

        # Compute fidelity: similarity between original and compressed reconstruction
        fidelity = _compute_reconstruction_fidelity(original_decode, comp_decode)

        results.append(CompressionBenchmarkResult(
            incident_type=incident.incident_id.split('_')[1],  # e.g., CPU_SPIKE
            method=method.name,
            target_ratio=ratio,
            achieved_ratio=comp_result.compression_ratio,
            fidelity_retention=fidelity,
            num_heus_original=len(heus),
            num_heus_compressed=len(comp_result.compressed_heus),
            solve_time_ms=original_solve_time,
            boundary_residual_original=original_result.boundary_residual,
            boundary_residual_compressed=comp_result_solve.boundary_residual,
        ))

    return results


def _compute_reconstruction_fidelity(decode1: Dict, decode2: Dict) -> float:
    """Compute cosine similarity between two decoded reconstructions, clamped to [0,1]."""
    # Flatten both to vectors
    vec1 = []
    vec2 = []

    all_services = set(decode1.get("services", {}).keys()) | set(decode2.get("services", {}).keys())
    all_dims = ["cpu_pressure", "memory_pressure", "network_latency", "error_rate",
                "config_change", "deployment_activity", "resource_contention", "service_dependency"]

    for svc in sorted(all_services):
        s1 = decode1.get("services", {}).get(svc, {})
        s2 = decode2.get("services", {}).get(svc, {})
        for dim in all_dims:
            vec1.append(s1.get(dim, 0.0))
            vec2.append(s2.get(dim, 0.0))

    vec1 = np.array(vec1)
    vec2 = np.array(vec2)

    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    sim = np.dot(vec1, vec2) / (norm1 * norm2)
    # Clamp to [0, 1]
    return float(np.clip(sim, 0.0, 1.0))


def run_full_benchmark() -> Dict[str, Any]:
    """Run comprehensive compression benchmark across all incident types and methods."""
    generator = SyntheticIncidentGenerator(seed=42)

    # Test incidents (just 2 for speed)
    incidents = [
        generator.generate(IncidentType.CPU_SPIKE_CASCADE),
        generator.generate(IncidentType.NETWORK_PARTITION),
    ]

    methods = [
        CompressionMethod.HYBRID,  # Just the best combined method for speed
    ]

    target_ratios = [2.0, 5.0, 10.0, 20.0]

    all_results = []

    print("Running compression benchmarks...")
    for incident in incidents:
        print(f"  Incident: {incident.incident_id}")
        for method in methods:
            try:
                results = run_compression_benchmark(incident, method, target_ratios)
                all_results.extend(results)
                for r in results:
                    print(f"    {method.name}: ratio={r.target_ratio:.0f}x -> {r.achieved_ratio:.1f}x, "
                          f"fidelity={r.fidelity_retention:.3f}, HEUs={r.num_heus_original}->{r.num_heus_compressed}")
            except Exception as e:
                print(f"    {method.name}: ERROR - {e}")

    # Summary statistics
    summary = _summarize_results(all_results)

    return {
        "individual_results": [asdict(r) for r in all_results],
        "summary": summary,
    }


def _summarize_results(results: List[CompressionBenchmarkResult]) -> Dict[str, Any]:
    """Generate summary statistics."""
    if not results:
        return {}

    by_method = {}
    for r in results:
        if r.method not in by_method:
            by_method[r.method] = []
        by_method[r.method].append(r)

    summary = {}
    for method, res_list in by_method.items():
        fidelities = [r.fidelity_retention for r in res_list]
        ratios = [r.achieved_ratio for r in res_list]

        summary[method] = {
            "mean_fidelity": float(np.mean(fidelities)),
            "std_fidelity": float(np.std(fidelities)),
            "min_fidelity": float(np.min(fidelities)),
            "max_fidelity": float(np.max(fidelities)),
            "mean_achieved_ratio": float(np.mean(ratios)),
            "num_runs": len(res_list),
            # Find max ratio with fidelity > 0.9
            "max_ratio_fidelity_90": max(
                [r.achieved_ratio for r in res_list if r.fidelity_retention >= 0.9],
                default=0
            ),
            "max_ratio_fidelity_80": max(
                [r.achieved_ratio for r in res_list if r.fidelity_retention >= 0.8],
                default=0
            ),
        }

    return summary


def save_results(results: Dict[str, Any], output_path: str = "compression_benchmark_results.json"):
    """Save benchmark results to JSON."""
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")


def print_summary(results: Dict[str, Any]):
    """Print human-readable summary."""
    print("\n" + "="*70)
    print("COMPRESSION BENCHMARK SUMMARY")
    print("="*70)

    for method, stats in results["summary"].items():
        print(f"\n{method}:")
        print(f"  Mean fidelity: {stats['mean_fidelity']:.3f} ± {stats['std_fidelity']:.3f}")
        print(f"  Fidelity range: {stats['min_fidelity']:.3f} - {stats['max_fidelity']:.3f}")
        print(f"  Mean achieved ratio: {stats['mean_achieved_ratio']:.1f}x")
        print(f"  Max ratio @ fidelity>=0.90: {stats['max_ratio_fidelity_90']:.1f}x")
        print(f"  Max ratio @ fidelity>=0.80: {stats['max_ratio_fidelity_80']:.1f}x")


if __name__ == "__main__":
    results = run_full_benchmark()
    save_results(results)
    print_summary(results)
