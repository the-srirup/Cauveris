# Cauveris CUDA Kernels

The compiled half of the holographic causal engine.  It evaluates the same
Green's functions as the NumPy reference implementation in
`cauveris/holographic/heu_kernel.py`, on the GPU.

## The split between Python and CUDA

The *policy* of the model - how fast a database publishes its metrics
compared with a queue, how long a scrape interval is compared with an
instrumented trace - lives in Python, in one place:
`cauveris/holographic/heu_kernel.py`.  The extension below receives the
characteristic time of every (component, boundary layer) pair and only
evaluates and convolves.

That split is deliberate.  A second copy of the policy written in CUDA would
be a second place for the two to drift apart, and the GPU would then answer a
slightly different question than the CPU.  `tests/holographic/test_gpu_kernels.py`
compares the two paths against each other, which is only a meaningful test
because they are supposed to compute the same thing.

## What the extension provides

| Function | What it does |
| --- | --- |
| `build_local_kernels(tau_ns, config, device_id)` | Evaluates the decay kernel of every (component, layer) pair: the density, its normalization, its peak and its half life. |
| `build_cross_kernels(src, dst, shifts, config, device_id)` | The cross propagation: the source kernel delayed by the transport delay of the edge and convolved with the local kernel of the target. |
| `assemble_kernel_matrix(values, rows, cols, ...)` | Writes the kernels into their slots of the measurement kernel matrix. |
| `matmul`, `batch_matmul`, `dot_product`, `l2_norm`, `l1_norm`, `scale_vector`, `axpy` | The linear algebra primitives. |
| `solve_cg_dense`, `solve_cg_csr` | Conjugate gradient, over a dense or a CSR matrix. |
| `solve_rls` | Ridge regression: the normal equations, a Cholesky factorization on the device and the triangular solves on the host in double precision. |
| `device_count`, `device_info` | What the CUDA runtime says about the device. |

Every function takes and returns host pointers (NumPy arrays) and moves the
data across the PCIe bus itself.  Handing a host pointer to a kernel is the
classic way to get silent garbage out of a CUDA program - the pointer is a
valid device address, it just does not point at the data - so the boundary is
drawn in one place instead of at every call site.

There is no `-use_fast_math`: the point of the GPU path is that it agrees
with the CPU path, and fast math swaps the transcendentals for
approximations.

## Building

The extension needs:

* a CUDA toolkit (12.x) - `nvcc` has to be on the `PATH`, or
  `CUDAToolkit_ROOT` has to point at it
* CMake 3.24 or newer
* Ninja
* a C++17 compiler
* Python 3.10 or newer with the development headers

On Windows, the compiler has to be MSVC **and** the Windows SDK has to be
installed - the SDK supplies the Universal C Runtime headers, without them
nothing that includes a standard header compiles.  The
"Desktop development with C++" workload of the Visual Studio Build Tools
includes both.

### No toolkit? Assemble one

NVIDIA's pip wheels for CUDA are not a toolkit.  `nvidia-cuda-nvcc-cu12`
ships `ptxas` and some headers, but no `nvcc`, and a build against it dies
during the compiler identification with a missing `libcudadevrt`.

NVIDIA publishes the same components as standalone archives.  The bootstrap
script downloads the three that are needed - the compiler, the runtime and
the C++ headers - and merges them into a toolkit root:

```bash
python cpp/scripts/bootstrap_cuda.py --root ./.cuda
cmake -S cpp -B cpp/build -G Ninja -DCUDAToolkit_ROOT=./.cuda
cmake --build cpp/build
```

That is about 85 MB, not the several gigabytes of the full toolkit.  The
script works the same way on Linux and on Windows; on Windows the Windows
SDK still has to be installed separately.

### Installing

```bash
pip install ./cpp
```

The build produces the top level module `cauveris_kernels_py`.  It is a
top level module on purpose: the `cauveris` Python package ships in the same
environment, and the extension must not fight with it over a directory name.

For a development build:

```bash
cmake -S cpp -B cpp/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build
```

`CMAKE_CUDA_ARCHITECTURES` defaults to `native`, which compiles for the GPU
of the build machine.  A build machine without a GPU (a CI runner, a
container) needs an explicit list, for example
`-DCMAKE_CUDA_ARCHITECTURES="80;86;89"`.

nvcc refuses to compile for a host compiler that is newer than the one it was
tested against.  The build passes `-allow-unsupported-compiler` by default;
turn it off with `-DCAUVERIS_ALLOW_UNSUPPORTED_COMPILER=OFF` when the two are
a matched pair.

## Using it

```python
from cauveris.holographic.gpu_kernels import (
    GPUConfig,
    create_gpu_kernel_builder,
    get_gpu_info,
    is_gpu_available,
)

print(get_gpu_info())

builder = create_gpu_kernel_builder(topology, GPUConfig())
builder.build_all_kernels()

kernel = builder.get_local_kernel("svc_a", "application_log")
cross = builder.get_cross_kernel("svc_a", "db_b", "application_log", "metrics_export")
```

`get_gpu_info()` reports what the engine would run on and, when there is
nothing to run on, why: the extension is not installed, the CUDA runtime
reports no device, or the driver knows about a GPU that the runtime cannot
reach.

The GPU is optional everywhere.  When it is not there, the builder falls back
to the NumPy reference and produces the same numbers - the fallback is what
`cauveris/holographic/gpu_kernels.py` runs on a machine without a GPU, and it
is covered by the tests as well.
