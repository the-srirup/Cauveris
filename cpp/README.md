# Cauveris GPU Kernels

GPU-accelerated holographic causal kernel engine for the Cauveris incident reconstruction platform.

## Features

- **Local Propagation Kernels**: Per-component, per-boundary-layer causal kernels with multiple decay functions (exponential, gamma, bi-exponential, power-law, stretched exponential)
- **Cross-Component Kernels**: Sparse causal dependency matrices built from system topology
- **Iterative Solvers**: Conjugate Gradient, ADMM, and Regularized Least Squares on GPU
- **Batched Operations**: High-performance batched convolution, matrix-vector multiply, and reductions
- **Mixed Precision**: FP16 storage with FP32 compute, Tensor Core support on Volta+

## Building

```bash
pip install -e .
```

## Usage

```python
from cauveris_kernels_py import (
    KernelConfig,
    LocalKernelBuilder,
    LocalKernelsGPU,
    CrossKernelBuilder,
    CrossKernelsGPU,
    ConjugateGradientSolver,
    ADMMSolver,
    RLSSolver,
    ComponentType,
    BoundaryLayer,
    DecayType,
    matmul,
    dot_product,
    l2_norm
)

# Configure
config = KernelConfig()
config.time_step_ns = 1e6
config.max_time_steps = 10000
config.num_components = 8

# Build local kernels
gpu_kernels = LocalKernelsGPU(batch_size=1, num_components=8, num_layers=8, time_steps=10000)
builder = LocalKernelBuilder(config)

component_ids = [0, 1, 2, 3, 4, 5, 6, 7]
component_types = [ComponentType.SERVICE] * 8

builder.build_kernels(gpu_kernels, component_ids, component_types, 8)

# Access kernel data
kernel_data = gpu_kernels.get_kernel_data()  # Returns numpy array
```