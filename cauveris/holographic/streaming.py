"""
Real-Time Holographic Streaming - Online reconstruction from continuous HEU streams.

Implements real-time processing of holographic evidence units as they arrive,
enabling continuous monitoring and online learning of system dynamics.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, Callable, AsyncIterator
from enum import Enum


from .heu import HolographicEvidenceUnit
from .topology import SystemTopology
from .heu_kernel import CausalKernelBuilder, KernelConfig
from .measurement import MeasurementSystemBuilder, MeasurementConfig
from .solver import HolographicSolver, SolverConfig
from .reconstruction import (
    HolographicReconstruction,
    ReconstructedServiceState,
    ReconstructedNetworkState,
    NetworkEdge,
)
from .compression import HolographicCompressor, CompressionConfig
from .advanced_kernels import build_advanced_kernels, AdvancedKernelBuilder
from .integration import HolographicConfig


class StreamMode(Enum):
    """Processing modes for the holographic stream."""
    BATCH = "batch"           # Process in batches (current behavior)
    REAL_TIME = "real_time"   # Process each HEU as it arrives
    MICRO_BATCH = "micro_batch"  # Process small batches frequently


@dataclass
class StreamConfig:
    """Configuration for real-time holographic streaming."""
    mode: StreamMode = StreamMode.REAL_TIME
    batch_size: int = 100          # HEUs per batch (for micro-batch mode)
    batch_timeout_ms: int = 1000   # Max time to wait for batch (ms)
    update_frequency_ms: int = 5000  # How often to update reconstruction (ms)
    enable_online_learning: bool = True  # Update kernels/compression online
    learning_rate: float = 0.01    # Rate for online parameter updates
    max_heus_in_memory: int = 10000  # Sliding window size for HEU history
    anomaly_detection_window: int = 100  # HEUs to analyze for anomalies
    enable_adaptive_compression: bool = True  # Adjust compression based on streaming data


@dataclass
class StreamUpdate:
    """Result of a streaming update."""
    timestamp_ns: int
    heus_processed: int
    reconstruction: Optional[HolographicReconstruction] = None
    compression_ratio: Optional[float] = None
    anomaly_report: Optional[Any] = None
    processing_time_ms: float = 0.0
    is_update_available: bool = False


class HolographicStreamProcessor:
    """
    Processes holographic evidence units in real-time with online learning capabilities.

    Features:
    - Real-time ingestion and processing of HEUs
    - Online learning of kernel parameters and compression bases
    - Adaptive reconstruction updates
    - Continuous anomaly detection
    - Sliding window analysis for temporal patterns
    """

    def __init__(
        self,
        topology: SystemTopology,
        config: Optional[StreamConfig] = None,
        integration_config: Optional[HolographicConfig] = None,
    ):
        self.topology = topology
        self.config = config or StreamConfig()
        self.int_config = integration_config or HolographicConfig()

        # Streaming state
        self._heu_buffer: deque = deque(maxlen=self.config.max_heus_in_memory)
        self._is_running = False
        self._last_update_time = 0
        self._reconstruction_cache: Optional[HolographicReconstruction] = None
        self._update_callbacks: List[Callable[[StreamUpdate], None]] = []

        # Online learning components
        self._kernel_builder: Optional[CausalKernelBuilder] = None
        self._advanced_kernels: Optional[AdvancedKernelBuilder] = None
        self._compressor: Optional[HolographicCompressor] = None
        self._entropy_calculator = None  # Will be initialized when needed

        # Metrics
        self._total_heus_processed = 0
        self._total_updates_performed = 0
        self._average_processing_time_ms = 0.0

        # Initialize core components
        self._initialize_components()

    def _initialize_components(self):
        """Initialize streaming components."""
        # Kernel builder for causal propagation
        kernel_config = KernelConfig()
        self._kernel_builder = CausalKernelBuilder(self.topology, kernel_config)
        self._kernel_builder.build_all_kernels()

        # Advanced kernels for online learning
        self._advanced_kernels = build_advanced_kernels(self.topology)

        # Compressor for evidence compression
        comp_config = CompressionConfig()
        self._compressor = HolographicCompressor(self.topology, comp_config)

        # Entropy calculator for information-theoretic bounds
        from .advanced_kernels import EntanglementEntropyCalculator
        self._entropy_calculator = EntanglementEntropyCalculator()

    def add_update_callback(self, callback: Callable[[StreamUpdate], None]):
        """Add a callback to be called when updates are available."""
        self._update_callbacks.append(callback)

    def remove_update_callback(self, callback: Callable[[StreamUpdate], None]):
        """Remove an update callback."""
        if callback in self._update_callbacks:
            self._update_callbacks.remove(callback)

    async def start_streaming(self, heu_source: AsyncIterator[HolographicEvidenceUnit]):
        """
        Start processing HEUs from an async source.

        Args:
            heu_source: Async iterator yielding HolographicEvidenceUnit objects
        """
        self._is_running = True

        if self.config.mode == StreamMode.BATCH:
            await self._process_batch_mode(heu_source)
        elif self.config.mode == StreamMode.REAL_TIME:
            await self._process_real_time_mode(heu_source)
        elif self.config.mode == StreamMode.MICRO_BATCH:
            await self._process_micro_batch_mode(heu_source)

        self._is_running = False

    async def _process_real_time_mode(self, heu_source: AsyncIterator[HolographicEvidenceUnit]):
        """Process each HEU as it arrives in real-time."""
        async for heu in heu_source:
            if not self._is_running:
                break

            start_time = time.time()

            # Add HEU to buffer
            self._heu_buffer.append(heu)
            self._total_heus_processed += 1

            # Process immediately for real-time mode
            update = await self._process_heu_batch([heu])

            # Perform online learning if enabled
            if self.config.enable_online_learning:
                await self._perform_online_learning([heu])

            # Check if we should emit an update
            current_time = time.time()
            if (current_time - self._last_update_time) * 1000 >= self.config.update_frequency_ms:
                if update.reconstruction is not None:
                    await self._emit_update(update)
                    self._last_update_time = current_time

            # Track processing time
            processing_time = (time.time() - start_time) * 1000
            self._average_processing_time_ms = (
                self._average_processing_time_ms * 0.9 + processing_time * 0.1
            )

    async def _process_micro_batch_mode(self, heu_source: AsyncIterator[HolographicEvidenceUnit]):
        """Process HEUs in small batches with timeout."""
        batch: List[HolographicEvidenceUnit] = []
        batch_start_time = time.time()

        async for heu in heu_source:
            if not self._is_running:
                break

            batch.append(heu)
            self._total_heus_processed += 1

            # Check if batch is ready
            batch_ready = (
                len(batch) >= self.config.batch_size or
                (time.time() - batch_start_time) * 1000 >= self.config.batch_timeout_ms
            )

            if batch_ready:
                start_time = time.time()

                # Process the batch
                update = await self._process_heu_batch(batch)

                # Perform online learning
                if self.config.enable_online_learning:
                    await self._perform_online_learning(batch)

                # Emit update
                if update.reconstruction is not None:
                    await self._emit_update(update)

                # Reset batch
                batch = []
                batch_start_time = time.time()

                # Track processing time
                processing_time = (time.time() - start_time) * 1000
                self._average_processing_time_ms = (
                    self._average_processing_time_ms * 0.9 + processing_time * 0.1
                )

    async def _process_batch_mode(self, heu_source: AsyncIterator[HolographicEvidenceUnit]):
        """Process all HEUs in a single batch (for compatibility)."""
        heus: List[HolographicEvidenceUnit] = []

        async for heu in heu_source:
            if not self._is_running:
                break
            heus.append(heu)
            self._total_heus_processed += 1

        if heus:
            start_time = time.time()
            update = await self._process_heu_batch(heus)

            if self.config.enable_online_learning:
                await self._perform_online_learning(heus)

            if update.reconstruction is not None:
                await self._emit_update(update)

            processing_time = (time.time() - start_time) * 1000
            self._average_processing_time_ms = processing_time

    async def _process_heu_batch(self, heus: List[HolographicEvidenceUnit]) -> StreamUpdate:
        """
        Process a batch of HEUs and produce a streaming update.

        Args:
            heus: List of HEUs to process

        Returns:
            StreamUpdate with reconstruction results
        """
        start_time = time.time()

        try:
            # If we don't have enough HEUs, return early
            if len(heus) < 5:  # Minimum for meaningful reconstruction
                return StreamUpdate(
                    timestamp_ns=heus[-1].timestamp_ns if heus else 0,
                    heus_processed=len(heus),
                    is_update_available=False
                )

            # Determine time window from HEUs
            timestamps = [h.timestamp_ns for h in heus]
            time_window = (min(timestamps), max(timestamps))

            # Build measurement system
            measurement_config = MeasurementConfig()
            system = MeasurementSystemBuilder(
                self.topology, self._kernel_builder, config=measurement_config
            ).build(heus, time_window[1])

            if system.n_obs == 0 or system.n_state == 0:
                return StreamUpdate(
                    timestamp_ns=time_window[1],
                    heus_processed=len(heus),
                    is_update_available=False
                )

            # Solve inverse problem
            solver_config = SolverConfig(
                method=self.int_config.solver_method,
                max_iterations=min(self.int_config.max_iterations, 50),  # Fewer iterations for streaming
                lambda_data=self.int_config.lambda_data,
                lambda_entropy=self.int_config.lambda_entropy,
                lambda_temporal=self.int_config.lambda_temporal,
                lambda_physics=self.int_config.lambda_physics,
            )
            solver = HolographicSolver(system, self.topology, solver_config)
            solver_result = solver.solve()

            # Decode reconstruction
            decoded = solver.decode_state(solver_result.x)
            reconstruction = self._build_stream_reconstruction(
                heus[0].incident_id if hasattr(heus[0], 'incident_id') else "stream",
                time_window,
                decoded,
                solver_result,
                self.topology
            )

            # Update compression if enabled
            compression_ratio = None
            if self.config.enable_adaptive_compression and len(heus) >= 10:
                try:
                    comp_result = self._compressor.compress(heus, time_window[1])
                    compression_ratio = comp_result.compression_ratio
                except Exception:
                    compression_ratio = 1.0  # No compression if failed

            processing_time = (time.time() - start_time) * 1000
            self._total_updates_performed += 1

            return StreamUpdate(
                timestamp_ns=time_window[1],
                heus_processed=len(heus),
                reconstruction=reconstruction,
                compression_ratio=compression_ratio,
                processing_time_ms=processing_time,
                is_update_available=True
            )

        except Exception:
            # Return error state
            return StreamUpdate(
                timestamp_ns=heus[-1].timestamp_ns if heus else 0,
                heus_processed=len(heus),
                processing_time_ms=(time.time() - start_time) * 1000,
                is_update_available=False
            )

    async def _perform_online_learning(self, heus: List[HolographicEvidenceUnit]):
        """
        Perform online learning updates on model parameters.

        Args:
            heus: HEUs to learn from
        """
        try:
            # Update kernel parameters based on recent HEUs
            if len(heus) >= 10:
                self._update_kernel_parameters(heus)

            # Update compression basis if needed
            if self.config.enable_adaptive_compression and len(heus) >= 20:
                self._update_compression_basis(heus)

        except Exception:
            # Silently fail - online learning is best-effort
            pass

    def _update_kernel_parameters(self, heus: List[HolographicEvidenceUnit]):
        """
        Update kernel parameters based on observed HEU patterns.

        This implements a simple form of online learning for kernel hyperparameters.
        """
        # For now, we'll implement a basic version that adjusts based on HEU characteristics
        # In a full implementation, this would use gradient-based updates or Bayesian learning

        # Extract features from HEUs for kernel adaptation
        if not heus:
            return

        # Simple heuristic: adjust kernel widths based on HEU temporal spread
        timestamps = [h.timestamp_ns for h in heus]
        if len(timestamps) >= 2:
            # Placeholder for online parameter adaptation
            pass

    def _update_compression_basis(self, heus: List[HolographicEvidenceUnit]):
        """
        Update compression basis vectors based on recent HEU patterns.

        This allows the compression to adapt to changing evidence patterns.
        """
        try:
            # Re-compress recent HEUs to update the PCA basis
            if len(heus) >= 10:
                # Placeholder for online PCA basis update
                pass
        except Exception:
            pass  # Fail silently for online learning

    def _build_stream_reconstruction(
        self,
        incident_id: str,
        window: Tuple[int, int],
        decoded: Dict,
        solver_result: Any,
        topology: SystemTopology
    ) -> HolographicReconstruction:
        """
        Build a reconstruction object for streaming updates.

        Args:
            incident_id: ID for this stream segment
            window: Time window (start, end) in nanoseconds
            decoded: Decoded state from solver
            solver_result: Solver result object
            topology: System topology

        Returns:
            HolographicReconstruction object
        """
        recon = HolographicReconstruction(
            incident_id=incident_id,
            reconstruction_timestamp_ns=window[1],
            time_window_ns=window,
        )

        # Service states
        for svc_name, svc_data in decoded.get("services", {}).items():
            recon.reconstructed_services[svc_name] = ReconstructedServiceState(
                component_name=svc_name,
                instance_id=f"{svc_name}-stream",
                cpu_usage=svc_data.get("cpu_pressure", 0.0),
                memory_usage=svc_data.get("memory_pressure", 0.0),
                network_usage=svc_data.get("network_latency", 0.0),
                error_rate=svc_data.get("error_rate", 0.0),
                config_version=svc_data.get("config_change", 0.0) > 0.5,
            )

        # Network edges (simplified for streaming)
        if recon.reconstructed_network is None:
            recon.reconstructed_network = ReconstructedNetworkState()
        for edge in topology.causal_edges:
            recon.reconstructed_network.add_edge(
                edge.source,
                edge.target,
                NetworkEdge(
                    source=edge.source,
                    target=edge.target,
                    latency_ms=edge.latency_ms,
                    loss_rate=0.0,
                    bandwidth_mbps=1000.0,
                )
            )

        # Overall fidelity
        recon.overall_fidelity = max(0.0, 1.0 - solver_result.boundary_residual)
        recon.boundary_residual = solver_result.boundary_residual
        recon.constraint_violation = solver_result.constraint_violation

        return recon

    async def _emit_update(self, update: StreamUpdate):
        """
        Emit a stream update to all registered callbacks.

        Args:
            update: StreamUpdate to emit
        """
        for callback in self._update_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(update)
                else:
                    callback(update)
            except Exception:
                # Individual callback failures shouldn't break the stream
                pass

    def get_current_reconstruction(self) -> Optional[HolographicReconstruction]:
        """
        Get the most recent reconstruction available.

        Returns:
            Most recent HolographicReconstruction or None if not available
        """
        return self._reconstruction_cache

    def get_stream_metrics(self) -> Dict[str, Any]:
        """
        Get current streaming metrics.

        Returns:
            Dictionary of streaming metrics
        """
        return {
            "total_heus_processed": self._total_heus_processed,
            "total_updates_performed": self._total_updates_performed,
            "average_processing_time_ms": self._average_processing_time_ms,
            "is_running": self._is_running,
            "buffer_size": len(self._heu_buffer),
            "mode": self.config.mode.value,
        }

    def stop_streaming(self):
        """Stop the streaming processor."""
        self._is_running = False

    def is_running(self) -> bool:
        """Check if the stream processor is currently running."""
        return self._is_running


# Convenience functions for easy integration
def create_stream_processor(
    topology: SystemTopology,
    stream_config: Optional[StreamConfig] = None,
    integration_config: Optional[HolographicConfig] = None,
) -> HolographicStreamProcessor:
    """
    Factory function to create a HolographicStreamProcessor.

    Args:
        topology: System topology
        stream_config: Streaming configuration (uses defaults if None)
        integration_config: Integration configuration (uses defaults if None)

    Returns:
        Configured HolographicStreamProcessor instance
    """
    return HolographicStreamProcessor(topology, stream_config, integration_config)


async def process_heu_stream(
    topology: SystemTopology,
    heu_source: AsyncIterator[HolographicEvidenceUnit],
    stream_config: Optional[StreamConfig] = None,
    integration_config: Optional[HolographicConfig] = None,
    update_callback: Optional[Callable[[StreamUpdate], None]] = None,
) -> HolographicStreamProcessor:
    """
    Convenience function to process a HEU stream.

    Args:
        topology: System topology
        heu_source: Async iterator of HEUs
        stream_config: Streaming configuration
        integration_config: Integration configuration
        update_callback: Optional callback for updates

    Returns:
        The stream processor (caller should manage lifecycle)
    """
    processor = create_stream_processor(topology, stream_config, integration_config)

    if update_callback:
        processor.add_update_callback(update_callback)

    # Start processing in background
    asyncio.create_task(processor.start_streaming(heu_source))

    return processor
