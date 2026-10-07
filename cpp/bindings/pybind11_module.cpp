/**
 * pybind11 Module for cauveris GPU Kernels.
 *
 * Exposes C++ CUDA engine to Python with NumPy array support.
 */

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>

#include "cauveris/kernel_types.h"
#include "cauveris/local_kernels.h"
#include "cauveris/cross_kernels.h"

#include <cuda_runtime.h>
#include <memory>
#include <vector>

namespace py = pybind11;
using namespace cauveris;

// ============================================================================
// Helper: NumPy Array to Device Pointer
// ============================================================================

template<typename T>
T* get_device_ptr(py::array_t<T>& arr) {
    if (!arr.is_contiguous()) {
        arr = py::array_t<T>(arr.shape(), arr.strides(), arr.data(), arr.parent());
    }
    return static_cast<T*>(arr.mutable_data());
}

template<typename T>
const T* get_device_ptr(const py::array_t<T>& arr) {
    if (!arr.is_contiguous()) {
        // Cannot make const array contiguous easily, require mutable
        throw std::runtime_error("Array must be C-contiguous");
    }
    return static_cast<const T*>(arr.data());
}

// ============================================================================
// Python Wrappers for GPU Structures
// ============================================================================

class PyLocalKernelsGPU {
public:
    PyLocalKernelsGPU(int batch_size = 1,
                      int num_components = 0,
                      int num_layers = static_cast<int>(BoundaryLayer::COUNT),
                      int time_steps = 0) {
        kernels_.allocate(batch_size, num_components, num_layers, time_steps);
    }

    ~PyLocalKernelsGPU() {
        kernels_.free();
    }

    int batch_size() const { return kernels_.batch_size; }
    int num_components() const { return kernels_.num_components; }
    int num_layers() const { return kernels_.num_layers; }
    int time_steps() const { return kernels_.time_steps; }

    // Get kernel data as NumPy array (copies from device)
    py::array_t<float> get_kernel_data() const {
        size_t total_size = static_cast<size_t>(kernels_.batch_size) *
                            kernels_.num_components * kernels_.num_layers * kernels_.time_steps;
        py::array_t<float> arr({kernels_.batch_size, kernels_.num_components, kernels_.num_layers, kernels_.time_steps});
        cudaMemcpy(arr.mutable_data(), kernels_.kernel_data, total_size * sizeof(float), cudaMemcpyDeviceToHost);
        return arr;
    }

    py::array_t<float> get_normalization_factors() const {
        size_t total_size = static_cast<size_t>(kernels_.batch_size) *
                            kernels_.num_components * kernels_.num_layers;
        py::array_t<float> arr({kernels_.batch_size, kernels_.num_components, kernels_.num_layers});
        cudaMemcpy(arr.mutable_data(), kernels_.normalization_factors, total_size * sizeof(float), cudaMemcpyDeviceToHost);
        return arr;
    }

    LocalKernelsGPU& get() { return kernels_; }
    const LocalKernelsGPU& get() const { return kernels_; }

private:
    LocalKernelsGPU kernels_;
};

class PyCrossKernelsGPU {
public:
    PyCrossKernelsGPU(int batch_size = 1, int num_components = 0, bool use_sparse = true) {
        kernels_.batch_size = batch_size;
        kernels_.num_components = num_components;
        kernels_.use_sparse = use_sparse;
        if (use_sparse) {
            // Will be allocated when building
        } else {
            kernels_.allocate_dense(batch_size, num_components);
        }
    }

    ~PyCrossKernelsGPU() {
        kernels_.free();
    }

    int batch_size() const { return kernels_.batch_size; }
    int num_components() const { return kernels_.num_components; }
    bool use_sparse() const { return kernels_.use_sparse; }
    int nnz() const { return kernels_.nnz; }

    py::array_t<float> get_dense_matrix() const {
        if (!kernels_.dense_matrix) {
            throw std::runtime_error("Dense matrix not allocated");
        }
        size_t total_size = static_cast<size_t>(kernels_.batch_size) *
                            kernels_.num_components * kernels_.num_components;
        py::array_t<float> arr({kernels_.batch_size, kernels_.num_components, kernels_.num_components});
        cudaMemcpy(arr.mutable_data(), kernels_.dense_matrix, total_size * sizeof(float), cudaMemcpyDeviceToHost);
        return arr;
    }

    CrossKernelsGPU& get() { return kernels_; }
    const CrossKernelsGPU& get() const { return kernels_; }

private:
    CrossKernelsGPU kernels_;
};

// ============================================================================
// Python Wrapper for KernelConfig
// ============================================================================

class PyKernelConfig {
public:
    PyKernelConfig() : config_() {}

    // Time parameters
    double time_step_ns;
    int64_t max_time_steps;

    // Spatial parameters
    int max_components;
    int max_boundary_layers;

    // Decay parameters
    int default_decay;  // DecayType enum value
    double default_decay_rate;
    double gamma_shape;
    double gamma_scale;
    double biexp_alpha;
    double biexp_lambda1;
    double biexp_lambda2;
    double power_law_alpha;
    double stretched_exp_tau;
    double stretched_exp_beta;

    // Normalization
    int normalization;  // NormalizationType enum value

    // GPU parameters
    int threads_per_block;
    int max_blocks;
    bool use_tensor_cores;
    bool enable_async;

    // Precision
    bool use_fp16_storage;
    bool use_mixed_precision;

    // Component decay rates (array of 9)
    std::vector<double> component_decay_rates;
    // Layer weights (array of 8)
    std::vector<double> layer_weights;

    PyKernelConfig() {
        time_step_ns = 1e6;
        max_time_steps = 10000;
        max_components = 1000;
        max_boundary_layers = 8;
        default_decay = static_cast<int>(DecayType::EXPONENTIAL);
        default_decay_rate = 1e-6;
        gamma_shape = 2.0;
        gamma_scale = 1e-6;
        biexp_alpha = 0.7;
        biexp_lambda1 = 1e-6;
        biexp_lambda2 = 1e-5;
        power_law_alpha = 1.5;
        stretched_exp_tau = 1e-6;
        stretched_exp_beta = 0.5;
        normalization = static_cast<int>(NormalizationType::CAUSAL_CONE);
        threads_per_block = 256;
        max_blocks = 65535;
        use_tensor_cores = true;
        enable_async = true;
        use_fp16_storage = false;
        use_mixed_precision = true;

        component_decay_rates.resize(9, default_decay_rate);
        layer_weights = {1.0, 0.8, 0.9, 1.2, 0.7, 0.5, 0.6, 0.4};
    }

    KernelConfig to_cpp() const {
        KernelConfig cfg;
        cfg.time_step_ns = time_step_ns;
        cfg.max_time_steps = max_time_steps;
        cfg.max_components = max_components;
        cfg.max_boundary_layers = max_boundary_layers;
        cfg.default_decay = static_cast<DecayType>(default_decay);
        cfg.default_decay_rate = default_decay_rate;
        cfg.gamma_shape = gamma_shape;
        cfg.gamma_scale = gamma_scale;
        cfg.biexp_alpha = biexp_alpha;
        cfg.biexp_lambda1 = biexp_lambda1;
        cfg.biexp_lambda2 = biexp_lambda2;
        cfg.power_law_alpha = power_law_alpha;
        cfg.stretched_exp_tau = stretched_exp_tau;
        cfg.stretched_exp_beta = stretched_exp_beta;
        cfg.normalization = static_cast<NormalizationType>(normalization);
        cfg.threads_per_block = threads_per_block;
        cfg.max_blocks = max_blocks;
        cfg.use_tensor_cores = use_tensor_cores;
        cfg.enable_async = enable_async;
        cfg.use_fp16_storage = use_fp16_storage;
        cfg.use_mixed_precision = use_mixed_precision;

        for (int i = 0; i < 9 && i < (int)component_decay_rates.size(); ++i) {
            cfg.component_decay_rates[i] = component_decay_rates[i];
        }
        for (int i = 0; i < 8 && i < (int)layer_weights.size(); ++i) {
            cfg.layer_weights[i] = layer_weights[i];
        }
        return cfg;
    }

    static PyKernelConfig from_cpp(const KernelConfig& cfg) {
        PyKernelConfig py_cfg;
        py_cfg.time_step_ns = cfg.time_step_ns;
        py_cfg.max_time_steps = cfg.max_time_steps;
        py_cfg.max_components = cfg.max_components;
        py_cfg.max_boundary_layers = cfg.max_boundary_layers;
        py_cfg.default_decay = static_cast<int>(cfg.default_decay);
        py_cfg.default_decay_rate = cfg.default_decay_rate;
        py_cfg.gamma_shape = cfg.gamma_shape;
        py_cfg.gamma_scale = cfg.gamma_scale;
        py_cfg.biexp_alpha = cfg.biexp_alpha;
        py_cfg.biexp_lambda1 = cfg.biexp_lambda1;
        py_cfg.biexp_lambda2 = cfg.biexp_lambda2;
        py_cfg.power_law_alpha = cfg.power_law_alpha;
        py_cfg.stretched_exp_tau = cfg.stretched_exp_tau;
        py_cfg.stretched_exp_beta = cfg.stretched_exp_beta;
        py_cfg.normalization = static_cast<int>(cfg.normalization);
        py_cfg.threads_per_block = cfg.threads_per_block;
        py_cfg.max_blocks = cfg.max_blocks;
        py_cfg.use_tensor_cores = cfg.use_tensor_cores;
        py_cfg.enable_async = cfg.enable_async;
        py_cfg.use_fp16_storage = cfg.use_fp16_storage;
        py_cfg.use_mixed_precision = cfg.use_mixed_precision;

        py_cfg.component_decay_rates.assign(cfg.component_decay_rates, cfg.component_decay_rates + 9);
        py_cfg.layer_weights.assign(cfg.layer_weights, cfg.layer_weights + 8);
        return py_cfg;
    }
};

// ============================================================================
// Python Wrapper for LocalKernelBuilder
// ============================================================================

class PyLocalKernelBuilder {
public:
    PyLocalKernelBuilder(const PyKernelConfig& config = PyKernelConfig())
        : builder_(config.to_cpp()) {}

    void build_kernels(PyLocalKernelsGPU& gpu_kernels,
                       const py::array_t<int>& component_ids,
                       const py::array_t<uint8_t>& component_types,
                       int num_components,
                       int batch_size = 1) {
        // Validate arrays
        if (component_ids.size() != num_components ||
            component_types.size() != num_components) {
            throw std::runtime_error("Array size mismatch");
        }

        // Get device pointers
        int* d_component_ids = get_device_ptr(component_ids);
        ComponentType* d_component_types = reinterpret_cast<ComponentType*>(get_device_ptr(component_types));

        builder_.build_kernels(gpu_kernels.get(), d_component_ids, d_component_types, num_components, batch_size);
    }

    void build_kernels_advanced(PyLocalKernelsGPU& gpu_kernels,
                                const py::array_t<int>& component_ids,
                                const py::array_t<uint8_t>& component_types,
                                const py::array_t<uint8_t>& decay_types,
                                const py::array_t<float>& decay_params,
                                int num_components,
                                const PyKernelConfig& config) {
        if (component_ids.size() != num_components ||
            component_types.size() != num_components) {
            throw std::runtime_error("Array size mismatch");
        }

        int total_pairs = num_components * static_cast<int>(BoundaryLayer::COUNT);
        if (decay_types.size() != total_pairs ||
            decay_params.size() != total_pairs * 4) {
            throw std::runtime_error("Advanced array size mismatch");
        }

        int* d_component_ids = get_device_ptr(component_ids);
        ComponentType* d_component_types = reinterpret_cast<ComponentType*>(get_device_ptr(component_types));
        uint8_t* d_decay_types = get_device_ptr(decay_types);
        float* d_decay_params = get_device_ptr(decay_params);

        // Call advanced build (need to add to builder)
        launch_build_local_kernels_advanced(gpu_kernels.get(), d_component_ids, d_component_types,
                                            d_decay_types, d_decay_params, num_components, config.to_cpp());
    }

private:
    LocalKernelBuilder builder_;
};

// ============================================================================
// Python Wrapper for CrossKernelBuilder
// ============================================================================

struct PyTopologyEdge {
    int source_id;
    int target_id;
    int source_type;  // ComponentType enum value
    int target_type;
    double latency_ns;
    double bandwidth_mbps;
    float causal_strength;
};

class PyCrossKernelBuilder {
public:
    PyCrossKernelBuilder(const PyKernelConfig& config = PyKernelConfig())
        : builder_(config.to_cpp()) {}

    void build_kernels(PyCrossKernelsGPU& gpu_kernels,
                       const std::vector<PyTopologyEdge>& edges,
                       int num_components,
                       int batch_size = 1) {
        // Convert edges to TopologyEdge array
        std::vector<TopologyEdge> cpp_edges;
        cpp_edges.reserve(edges.size());
        for (const auto& e : edges) {
            TopologyEdge te;
            te.source_id = e.source_id;
            te.target_id = e.target_id;
            te.source_type = static_cast<ComponentType>(e.source_type);
            te.target_type = static_cast<ComponentType>(e.target_type);
            te.latency_ns = e.latency_ns;
            te.bandwidth_mbps = e.bandwidth_mbps;
            te.causal_strength = e.causal_strength;
            cpp_edges.push_back(te);
        }

        // Allocate device memory
        TopologyEdge* d_edges;
        cudaMalloc(&d_edges, cpp_edges.size() * sizeof(TopologyEdge));
        cudaMemcpy(d_edges, cpp_edges.data(), cpp_edges.size() * sizeof(TopologyEdge), cudaMemcpyHostToDevice);

        builder_.build_kernels(gpu_kernels.get(), d_edges, static_cast<int>(cpp_edges.size()), num_components, batch_size);

        cudaFree(d_edges);
    }

    void build_from_adjacency(PyCrossKernelsGPU& gpu_kernels,
                              const py::array_t<int>& row_ptr,
                              const py::array_t<int>& col_idx,
                              const py::array_t<float>& weights,
                              int num_components,
                              int batch_size = 1) {
        int* d_row_ptr = get_device_ptr(row_ptr);
        int* d_col_idx = get_device_ptr(col_idx);
        float* d_weights = get_device_ptr(weights);

        builder_.build_from_adjacency(gpu_kernels.get(), d_row_ptr, d_col_idx, d_weights,
                                      num_components, batch_size);
    }

private:
    CrossKernelBuilder builder_;
};

// ============================================================================
// Solver Wrappers
// ============================================================================

class PyConjugateGradientSolver {
public:
    PyConjugateGradientSolver(bool use_sparse = true) : solver_(use_sparse) {}

    py::array_t<float> solve(const py::array_t<float>& A_dense,
                             const py::array_t<int>& row_ptr,
                             const py::array_t<int>& col_idx,
                             const py::array_t<float>& values,
                             const py::array_t<float>& b,
                             int max_iter = 1000,
                             float tol = 1e-6f) {
        int n = b.size();
        py::array_t<float> x({n});

        const float* d_A = A_dense.size() > 0 ? get_device_ptr(A_dense) : nullptr;
        const int* d_row_ptr = row_ptr.size() > 0 ? get_device_ptr(row_ptr) : nullptr;
        const int* d_col_idx = col_idx.size() > 0 ? get_device_ptr(col_idx) : nullptr;
        const float* d_values = values.size() > 0 ? get_device_ptr(values) : nullptr;
        const float* d_b = get_device_ptr(b);
        float* d_x = get_device_ptr(x);

        solver_.solve(d_A, d_row_ptr, d_col_idx, d_values, d_b, d_x, n, max_iter, tol);

        return x;
    }

private:
    ConjugateGradientSolver solver_;
};

class PyADMMSolver {
public:
    PyADMMSolver() {}

    py::array_t<float> solve(const py::array_t<float>& A_dense,
                             const py::array_t<float>& b,
                             const py::array_t<float>& lambda,
                             int max_iter = 1000,
                             float primal_tol = 1e-4f,
                             float dual_tol = 1e-4f,
                             float rho = 1.0f) {
        int m = A_dense.shape(0);
        int n = A_dense.shape(1);

        if (b.size() != m || lambda.size() != n) {
            throw std::runtime_error("Dimension mismatch");
        }

        py::array_t<float> x({n});

        const float* d_A = get_device_ptr(A_dense);
        const float* d_b = get_device_ptr(b);
        const float* d_lambda = get_device_ptr(lambda);
        float* d_x = get_device_ptr(x);

        ADMMSolver solver;
        solver.solve(d_A, d_b, d_lambda, d_x, m, n, max_iter, primal_tol, dual_tol, rho);

        return x;
    }
};

class PyRLSSolver {
public:
    PyRLSSolver() {}

    py::array_t<float> solve(const py::array_t<float>& A_dense,
                             const py::array_t<float>& b,
                             const py::array_t<float>& lambda) {
        int m = A_dense.shape(0);
        int n = A_dense.shape(1);

        if (b.size() != m || lambda.size() != n) {
            throw std::runtime_error("Dimension mismatch");
        }

        py::array_t<float> x({n});

        const float* d_A = get_device_ptr(A_dense);
        const float* d_b = get_device_ptr(b);
        const float* d_lambda = get_device_ptr(lambda);
        float* d_x = get_device_ptr(x);

        RLSSolver solver;
        solver.solve(d_A, d_b, d_lambda, d_x, m, n);

        return x;
    }
};

// ============================================================================
// Utility Functions
// ============================================================================

py::array_t<float> gpu_matmul(const py::array_t<float>& A, const py::array_t<float>& B) {
    int m = A.shape(0);
    int k = A.shape(1);
    int k2 = B.shape(0);
    int n = B.shape(1);

    if (k != k2) throw std::runtime_error("Dimension mismatch");

    py::array_t<float> C({m, n});
    const float* d_A = get_device_ptr(A);
    const float* d_B = get_device_ptr(B);
    float* d_C = get_device_ptr(C);

    launch_matmul(d_A, d_B, d_C, m, n, k);
    return C;
}

py::array_t<float> gpu_batch_matmul(const py::array_t<float>& A, const py::array_t<float>& B) {
    int batch = A.shape(0);
    int m = A.shape(1);
    int k = A.shape(2);
    int k2 = B.shape(1);
    int n = B.shape(2);

    if (k != k2) throw std::runtime_error("Dimension mismatch");

    py::array_t<float> C({batch, m, n});
    const float* d_A = get_device_ptr(A);
    const float* d_B = get_device_ptr(B);
    float* d_C = get_device_ptr(C);

    launch_matmul_batched(d_A, d_B, d_C, batch, m, n, k);
    return C;
}

float gpu_dot_product(const py::array_t<float>& a, const py::array_t<float>& b) {
    if (a.size() != b.size()) throw std::runtime_error("Size mismatch");
    const float* d_a = get_device_ptr(a);
    const float* d_b = get_device_ptr(b);
    return launch_dot_product(d_a, d_b, a.size());
}

float gpu_l2_norm(const py::array_t<float>& x) {
    const float* d_x = get_device_ptr(x);
    return launch_l2_norm(d_x, x.size());
}

float gpu_l1_norm(const py::array_t<float>& x) {
    const float* d_x = get_device_ptr(x);
    return launch_l1_norm(d_x, x.size());
}

py::array_t<float> gpu_scale(const py::array_t<float>& x, float alpha) {
    py::array_t<float> y(x.shape());
    const float* d_x = get_device_ptr(x);
    float* d_y = get_device_ptr(y);
    launch_scale_vector(d_y, d_x, alpha, x.size());
    return y;
}

py::array_t<float> gpu_axpy(py::array_t<float>& y, const py::array_t<float>& x, float alpha) {
    if (y.size() != x.size()) throw std::runtime_error("Size mismatch");
    float* d_y = get_device_ptr(y);
    const float* d_x = get_device_ptr(x);
    launch_axpy(d_y, d_x, alpha, y.size());
    return y;
}

// ============================================================================
// Module Definition
// ============================================================================

PYBIND11_MODULE(cauveris_kernels_py, m) {
    m.doc() = "Cauveris GPU-Accelerated Holographic Kernel Engine";

    // Enums
    py::enum_<BoundaryLayer>(m, "BoundaryLayer")
        .value("APPLICATION_LOG", BoundaryLayer::APPLICATION_LOG)
        .value("INFRASTRUCTURE_LOG", BoundaryLayer::INFRASTRUCTURE_LOG)
        .value("METRICS_EXPORT", BoundaryLayer::METRICS_EXPORT)
        .value("DISTRIBUTED_TRACE", BoundaryLayer::DISTRIBUTED_TRACE)
        .value("NETWORK_PACKET", BoundaryLayer::NETWORK_PACKET)
        .value("HEARTBEAT_BEACON", BoundaryLayer::HEARTBEAT_BEACON)
        .value("CONFIG_SNAPSHOT", BoundaryLayer::CONFIG_SNAPSHOT)
        .value("SECURITY_AUDIT", BoundaryLayer::SECURITY_AUDIT)
        .export_values();

    py::enum_<ComponentType>(m, "ComponentType")
        .value("UNKNOWN", ComponentType::UNKNOWN)
        .value("SERVICE", ComponentType::SERVICE)
        .value("DATABASE", ComponentType::DATABASE)
        .value("CACHE", ComponentType::CACHE)
        .value("MESSAGE_QUEUE", ComponentType::MESSAGE_QUEUE)
        .value("GATEWAY", ComponentType::GATEWAY)
        .value("LOAD_BALANCER", ComponentType::LOAD_BALANCER)
        .value("PROXY", ComponentType::PROXY)
        .value("SIDECAR", ComponentType::SIDECAR)
        .export_values();

    py::enum_<DecayType>(m, "DecayType")
        .value("EXPONENTIAL", DecayType::EXPONENTIAL)
        .value("GAMMA", DecayType::GAMMA)
        .value("BI_EXPONENTIAL", DecayType::BI_EXPONENTIAL)
        .value("POWER_LAW", DecayType::POWER_LAW)
        .value("STRETCHED_EXP", DecayType::STRETCHED_EXP)
        .export_values();

    py::enum_<NormalizationType>(m, "NormalizationType")
        .value("NONE", NormalizationType::NONE)
        .value("L1_NORM", NormalizationType::L1_NORM)
        .value("L2_NORM", NormalizationType::L2_NORM)
        .value("MAX_NORM", NormalizationType::MAX_NORM)
        .value("CAUSAL_CONE", NormalizationType::CAUSAL_CONE)
        .export_values();

    // KernelConfig
    py::class_<PyKernelConfig>(m, "KernelConfig")
        .def(py::init<>())
        .def_readwrite("time_step_ns", &PyKernelConfig::time_step_ns)
        .def_readwrite("max_time_steps", &PyKernelConfig::max_time_steps)
        .def_readwrite("max_components", &PyKernelConfig::max_components)
        .def_readwrite("max_boundary_layers", &PyKernelConfig::max_boundary_layers)
        .def_readwrite("default_decay", &PyKernelConfig::default_decay)
        .def_readwrite("default_decay_rate", &PyKernelConfig::default_decay_rate)
        .def_readwrite("gamma_shape", &PyKernelConfig::gamma_shape)
        .def_readwrite("gamma_scale", &PyKernelConfig::gamma_scale)
        .def_readwrite("biexp_alpha", &PyKernelConfig::biexp_alpha)
        .def_readwrite("biexp_lambda1", &PyKernelConfig::biexp_lambda1)
        .def_readwrite("biexp_lambda2", &PyKernelConfig::biexp_lambda2)
        .def_readwrite("power_law_alpha", &PyKernelConfig::power_law_alpha)
        .def_readwrite("stretched_exp_tau", &PyKernelConfig::stretched_exp_tau)
        .def_readwrite("stretched_exp_beta", &PyKernelConfig::stretched_exp_beta)
        .def_readwrite("normalization", &PyKernelConfig::normalization)
        .def_readwrite("threads_per_block", &PyKernelConfig::threads_per_block)
        .def_readwrite("max_blocks", &PyKernelConfig::max_blocks)
        .def_readwrite("use_tensor_cores", &PyKernelConfig::use_tensor_cores)
        .def_readwrite("enable_async", &PyKernelConfig::enable_async)
        .def_readwrite("use_fp16_storage", &PyKernelConfig::use_fp16_storage)
        .def_readwrite("use_mixed_precision", &PyKernelConfig::use_mixed_precision)
        .def_readwrite("component_decay_rates", &PyKernelConfig::component_decay_rates)
        .def_readwrite("layer_weights", &PyKernelConfig::layer_weights);

    // LocalKernelsGPU
    py::class_<PyLocalKernelsGPU>(m, "LocalKernelsGPU")
        .def(py::init<int, int, int, int>(),
             py::arg("batch_size") = 1,
             py::arg("num_components") = 0,
             py::arg("num_layers") = 8,
             py::arg("time_steps") = 0)
        .def_readonly("batch_size", &PyLocalKernelsGPU::batch_size)
        .def_readonly("num_components", &PyLocalKernelsGPU::num_components)
        .def_readonly("num_layers", &PyLocalKernelsGPU::num_layers)
        .def_readonly("time_steps", &PyLocalKernelsGPU::time_steps)
        .def("get_kernel_data", &PyLocalKernelsGPU::get_kernel_data)
        .def("get_normalization_factors", &PyLocalKernelsGPU::get_normalization_factors);

    // CrossKernelsGPU
    py::class_<PyCrossKernelsGPU>(m, "CrossKernelsGPU")
        .def(py::init<int, int, bool>(),
             py::arg("batch_size") = 1,
             py::arg("num_components") = 0,
             py::arg("use_sparse") = true)
        .def_readonly("batch_size", &PyCrossKernelsGPU::batch_size)
        .def_readonly("num_components", &PyCrossKernelsGPU::num_components)
        .def_readonly("use_sparse", &PyCrossKernelsGPU::use_sparse)
        .def_readonly("nnz", &PyCrossKernelsGPU::nnz)
        .def("get_dense_matrix", &PyCrossKernelsGPU::get_dense_matrix);

    // LocalKernelBuilder
    py::class_<PyLocalKernelBuilder>(m, "LocalKernelBuilder")
        .def(py::init<const PyKernelConfig&>(), py::arg("config") = PyKernelConfig())
        .def("build_kernels", &PyLocalKernelBuilder::build_kernels,
             py::arg("gpu_kernels"),
             py::arg("component_ids"),
             py::arg("component_types"),
             py::arg("num_components"),
             py::arg("batch_size") = 1)
        .def("build_kernels_advanced", &PyLocalKernelBuilder::build_kernels_advanced,
             py::arg("gpu_kernels"),
             py::arg("component_ids"),
             py::arg("component_types"),
             py::arg("decay_types"),
             py::arg("decay_params"),
             py::arg("num_components"),
             py::arg("config"));

    // CrossKernelBuilder
    py::class_<PyTopologyEdge>(m, "TopologyEdge")
        .def(py::init<>())
        .def_readwrite("source_id", &PyTopologyEdge::source_id)
        .def_readwrite("target_id", &PyTopologyEdge::target_id)
        .def_readwrite("source_type", &PyTopologyEdge::source_type)
        .def_readwrite("target_type", &PyTopologyEdge::target_type)
        .def_readwrite("latency_ns", &PyTopologyEdge::latency_ns)
        .def_readwrite("bandwidth_mbps", &PyTopologyEdge::bandwidth_mbps)
        .def_readwrite("causal_strength", &PyTopologyEdge::causal_strength);

    py::class_<PyCrossKernelBuilder>(m, "CrossKernelBuilder")
        .def(py::init<const PyKernelConfig&>(), py::arg("config") = PyKernelConfig())
        .def("build_kernels", &PyCrossKernelBuilder::build_kernels,
             py::arg("gpu_kernels"),
             py::arg("edges"),
             py::arg("num_components"),
             py::arg("batch_size") = 1)
        .def("build_from_adjacency", &PyCrossKernelBuilder::build_from_adjacency,
             py::arg("gpu_kernels"),
             py::arg("row_ptr"),
             py::arg("col_idx"),
             py::arg("weights"),
             py::arg("num_components"),
             py::arg("batch_size") = 1);

    // Solvers
    py::class_<PyConjugateGradientSolver>(m, "ConjugateGradientSolver")
        .def(py::init<bool>(), py::arg("use_sparse") = true)
        .def("solve", &PyConjugateGradientSolver::solve,
             py::arg("A_dense"),
             py::arg("row_ptr"),
             py::arg("col_idx"),
             py::arg("values"),
             py::arg("b"),
             py::arg("max_iter") = 1000,
             py::arg("tol") = 1e-6f);

    py::class_<PyADMMSolver>(m, "ADMMSolver")
        .def(py::init<>())
        .def("solve", &PyADMMSolver::solve,
             py::arg("A_dense"),
             py::arg("b"),
             py::arg("lambda"),
             py::arg("max_iter") = 1000,
             py::arg("primal_tol") = 1e-4f,
             py::arg("dual_tol") = 1e-4f,
             py::arg("rho") = 1.0f);

    py::class_<PyRLSSolver>(m, "RLSSolver")
        .def(py::init<>())
        .def("solve", &PyRLSSolver::solve,
             py::arg("A_dense"),
             py::arg("b"),
             py::arg("lambda"));

    // Utility functions
    m.def("matmul", &gpu_matmul, "Matrix multiplication on GPU");
    m.def("batch_matmul", &gpu_batch_matmul, "Batched matrix multiplication on GPU");
    m.def("dot_product", &gpu_dot_product, "Dot product on GPU");
    m.def("l2_norm", &gpu_l2_norm, "L2 norm on GPU");
    m.def("l1_norm", &gpu_l1_norm, "L1 norm on GPU");
    m.def("scale", &gpu_scale, "Scale vector on GPU");
    m.def("axpy", &gpu_axpy, "AXPY (y += alpha * x) on GPU");

    // Version info
    m.attr("__version__") = "0.1.0";
    m.attr("__cuda_version__") = "12.0";
}