/**
 * Core type definitions for the holographic causal kernel engine.
 *
 * Provides type-safe structures for boundary-bulk propagation kernels
 * with support for multiple decay functions and normalization schemes.
 */

#pragma once

#include <cstdint>
#include <cstddef>
#include <vector>
#include <string>

namespace cauveris {

// Forward declarations
struct LocalPropagationKernel;
struct CrossPropagationKernel;
struct KernelConfig;

// ============================================================================
// Enumerations
// ============================================================================

enum class BoundaryLayer : uint8_t {
    APPLICATION_LOG       = 0,
    INFRASTRUCTURE_LOG    = 1,
    METRICS_EXPORT        = 2,
    DISTRIBUTED_TRACE     = 3,
    NETWORK_PACKET        = 4,
    HEARTBEAT_BEACON      = 5,
    CONFIG_SNAPSHOT       = 6,
    SECURITY_AUDIT        = 7,
    COUNT                 = 8
};

enum class ComponentType : uint8_t {
    UNKNOWN       = 0,
    SERVICE       = 1,
    DATABASE      = 2,
    CACHE         = 3,
    MESSAGE_QUEUE = 4,
    GATEWAY       = 5,
    LOAD_BALANCER = 6,
    PROXY         = 7,
    SIDECAR       = 8,
    COUNT         = 9
};

enum class DecayType : uint8_t {
    EXPONENTIAL     = 0,    // exp(-λt)
    GAMMA           = 1,    // t^(k-1) * exp(-t/θ)
    BI_EXPONENTIAL  = 2,    // a*exp(-λ₁t) + (1-a)*exp(-λ₂t)
    POWER_LAW       = 3,    // t^(-α)
    STRETCHED_EXP   = 4,    // exp(-(t/τ)^β)
    COUNT           = 5
};

enum class NormalizationType : uint8_t {
    NONE            = 0,
    L1_NORM         = 1,
    L2_NORM         = 2,
    MAX_NORM        = 3,
    CAUSAL_CONE     = 4,    // Normalize within causal cone only
    COUNT           = 5
};

// ============================================================================
// Configuration Structures
// ============================================================================

struct KernelConfig {
    // Temporal parameters
    double time_step_ns = 1e6;          // 1ms default time step
    int64_t max_time_steps = 10000;     // 10s default window

    // Spatial parameters
    int max_components = 1000;
    int max_boundary_layers = static_cast<int>(BoundaryLayer::COUNT);

    // Kernel parameters
    DecayType default_decay = DecayType::EXPONENTIAL;
    double default_decay_rate = 1e-6;   // λ for exponential
    double gamma_shape = 2.0;           // k for gamma
    double gamma_scale = 1e-6;          // θ for gamma
    double biexp_alpha = 0.7;           // a for bi-exponential
    double biexp_lambda1 = 1e-6;
    double biexp_lambda2 = 1e-5;
    double power_law_alpha = 1.5;
    double stretched_exp_tau = 1e-6;
    double stretched_exp_beta = 0.5;

    // Normalization
    NormalizationType normalization = NormalizationType::CAUSAL_CONE;

    // GPU parameters
    int threads_per_block = 256;
    int max_blocks = 65535;
    bool use_tensor_cores = true;
    bool enable_async = true;

    // Precision
    bool use_fp16_storage = false;      // Store in FP16, compute in FP32
    bool use_mixed_precision = true;

    // Component-specific decay overrides
    double component_decay_rates[static_cast<int>(ComponentType::COUNT)];
    double layer_weights[static_cast<int>(BoundaryLayer::COUNT)];

    KernelConfig() {
        for (int i = 0; i < static_cast<int>(ComponentType::COUNT); ++i) {
            component_decay_rates[i] = default_decay_rate;
        }
        // Default layer weights (can be calibrated per system)
        layer_weights[static_cast<int>(BoundaryLayer::APPLICATION_LOG)]       = 1.0;
        layer_weights[static_cast<int>(BoundaryLayer::INFRASTRUCTURE_LOG)]    = 0.8;
        layer_weights[static_cast<int>(BoundaryLayer::METRICS_EXPORT)]        = 0.9;
        layer_weights[static_cast<int>(BoundaryLayer::DISTRIBUTED_TRACE)]     = 1.2;
        layer_weights[static_cast<int>(BoundaryLayer::NETWORK_PACKET)]        = 0.7;
        layer_weights[static_cast<int>(BoundaryLayer::HEARTBEAT_BEACON)]      = 0.5;
        layer_weights[static_cast<int>(BoundaryLayer::CONFIG_SNAPSHOT)]       = 0.6;
        layer_weights[static_cast<int>(BoundaryLayer::SECURITY_AUDIT)]        = 0.4;
    }
};

// ============================================================================
// Local Propagation Kernel (per-component, per-layer)
// ============================================================================

struct LocalPropagationKernel {
    // Component identification
    int component_id = -1;
    ComponentType component_type = ComponentType::UNKNOWN;
    BoundaryLayer layer = BoundaryLayer::APPLICATION_LOG;

    // Kernel data (SOA layout for GPU efficiency)
    // Stored as flat array: [time_steps]
    float* kernel_values = nullptr;      // Device pointer
    int time_steps = 0;

    // Decay parameters
    DecayType decay_type = DecayType::EXPONENTIAL;
    double decay_params[4] = {0};        // Up to 4 parameters depending on decay type

    // Normalization factor
    float normalization_factor = 1.0f;

    // Metadata
    double layer_weight = 1.0;
    bool is_valid = false;
    int64_t timestamp_ns = 0;

    // Host-side vectors for building
    std::vector<float> host_kernel_values;

    LocalPropagationKernel() = default;
    ~LocalPropagationKernel();

    // Disable copy (manage GPU memory explicitly)
    LocalPropagationKernel(const LocalPropagationKernel&) = delete;
    LocalPropagationKernel& operator=(const LocalPropagationKernel&) = delete;

    // Move semantics
    LocalPropagationKernel(LocalPropagationKernel&& other) noexcept;
    LocalPropagationKernel& operator=(LocalPropagationKernel&& other) noexcept;

    // Build kernel on host
    void build_host(const KernelConfig& config);

    // Upload to device
    void upload_to_device();

    // Download from device
    void download_from_device();

    // Get kernel value at time step
    __device__ __host__ float get_value(int t) const {
        if (t >= 0 && t < time_steps && kernel_values) {
            return kernel_values[t];
        }
        return 0.0f;
    }
};

// ============================================================================
// Cross Propagation Kernel (component-to-component)
// ============================================================================

struct CrossPropagationKernel {
    // Component pair identification
    int source_id = -1;
    int target_id = -1;
    ComponentType source_type = ComponentType::UNKNOWN;
    ComponentType target_type = ComponentType::UNKNOWN;

    // Kernel matrix entry (for sparse representation)
    // Only stores non-zero entries within causal cone
    struct SparseEntry {
        int target_idx;
        float weight;
    };

    // Host-side sparse representation
    std::vector<SparseEntry> sparse_entries;

    // Device-side dense matrix (for small systems) or CSR (for large)
    float* dense_matrix = nullptr;       // [max_components * max_components]
    int* csr_row_ptr = nullptr;          // [max_components + 1]
    int* csr_col_idx = nullptr;          // [nnz]
    float* csr_values = nullptr;         // [nnz]
    int nnz = 0;
    bool use_sparse = true;

    // Metadata
    double causal_strength = 1.0;
    int64_t timestamp_ns = 0;
    bool is_valid = false;

    CrossPropagationKernel() = default;
    ~CrossPropagationKernel();

    CrossPropagationKernel(const CrossPropagationKernel&) = delete;
    CrossPropagationKernel& operator=(const CrossPropagationKernel&) = delete;

    CrossPropagationKernel(CrossPropagationKernel&& other) noexcept;
    CrossPropagationKernel& operator=(CrossPropagationKernel&& other) noexcept;

    void build_host(const KernelConfig& config, int num_components);
    void upload_to_device();
    void download_from_device();
};

// ============================================================================
// GPU Device Structures (SOA layout for coalesced access)
// ============================================================================

struct LocalKernelsGPU {
    // SOA: [batch][component][layer][time]
    float* kernel_data = nullptr;        // Flattened: batch * num_components * num_layers * time_steps
    float* normalization_factors = nullptr; // [batch * num_components * num_layers]

    int batch_size = 1;
    int num_components = 0;
    int num_layers = static_cast<int>(BoundaryLayer::COUNT);
    int time_steps = 0;

    // Decay parameters per component-layer (packed)
    float* decay_params = nullptr;       // [batch * num_components * num_layers * 4]
    uint8_t* decay_types = nullptr;      // [batch * num_components * num_layers]

    // Layer weights
    float* layer_weights = nullptr;      // [num_layers]

    LocalKernelsGPU() = default;
    ~LocalKernelsGPU();

    void allocate(int batch, int components, int layers, int time_steps);
    void free();

    __device__ float* get_kernel_ptr(int batch, int comp, int layer) {
        if (!kernel_data || batch >= batch_size || comp >= num_components || layer >= num_layers) return nullptr;
        size_t offset = ((batch * num_components + comp) * num_layers + layer) * time_steps;
        return kernel_data + offset;
    }

    __device__ float get_normalization(int batch, int comp, int layer) const {
        if (!normalization_factors || batch >= batch_size || comp >= num_components || layer >= num_layers) return 1.0f;
        return normalization_factors[batch * num_components * num_layers + comp * num_layers + layer];
    }
};

struct CrossKernelsGPU {
    // Dense matrix: [batch][source][target]
    float* dense_matrix = nullptr;

    // CSR for sparse
    int* csr_row_ptr = nullptr;
    int* csr_col_idx = nullptr;
    float* csr_values = nullptr;

    int batch_size = 1;
    int num_components = 0;
    int nnz = 0;
    bool use_sparse = true;

    CrossKernelsGPU() = default;
    ~CrossKernelsGPU();

    void allocate_dense(int batch, int components);
    void allocate_sparse(int batch, int components, int nnz);
    void free();

    __device__ float get_dense(int batch, int src, int dst) const {
        if (!dense_matrix || batch >= batch_size || src >= num_components || dst >= num_components) return 0.0f;
        return dense_matrix[batch * num_components * num_components + src * num_components + dst];
    }
};

// ============================================================================
// Solver State Structures
// ============================================================================

struct CGState {
    float* x = nullptr;          // Solution vector
    float* r = nullptr;          // Residual
    float* p = nullptr;          // Search direction
    float* Ap = nullptr;         // A * p
    float* z = nullptr;          // Preconditioned residual (for PCG)

    float alpha = 0.0f;
    float beta = 0.0f;
    float rz_old = 0.0f;
    float rz_new = 0.0f;

    int max_iterations = 1000;
    float tolerance = 1e-6f;
    int iterations = 0;
    float residual_norm = 0.0f;
    bool converged = false;

    CGState() = default;
    ~CGState();

    void allocate(int n);
    void free();
};

struct ADMMState {
    float* x = nullptr;          // Primal variable
    float* z = nullptr;          // Auxiliary variable
    float* u = nullptr;          // Dual variable (scaled)

    float* x_prev = nullptr;     // Previous x for convergence check

    float rho = 1.0f;            // Augmented Lagrangian parameter
    float alpha = 1.0f;          // Relaxation parameter

    int max_iterations = 1000;
    float primal_tol = 1e-4f;
    float dual_tol = 1e-4f;
    int iterations = 0;
    float primal_residual = 0.0f;
    float dual_residual = 0.0f;
    bool converged = false;

    ADMMState() = default;
    ~ADMMState();

    void allocate(int n);
    void free();
};

struct RLSState {
    float* A = nullptr;          // Design matrix [m x n]
    float* b = nullptr;          // Observation vector [m]
    float* x = nullptr;          // Solution [n]
    float* lambda = nullptr;     // Regularization params [n]

    float* ATA = nullptr;        // A^T A [n x n]
    float* ATb = nullptr;        // A^T b [n]

    int m = 0;                   // Rows (observations)
    int n = 0;                   // Cols (variables)

    RLSState() = default;
    ~RLSState();

    void allocate(int m_, int n_);
    void free();
};

// ============================================================================
// Utility Functions
// ============================================================================

inline const char* boundary_layer_to_string(BoundaryLayer layer) {
    static const char* names[] = {
        "APPLICATION_LOG", "INFRASTRUCTURE_LOG", "METRICS_EXPORT", "DISTRIBUTED_TRACE",
        "NETWORK_PACKET", "HEARTBEAT_BEACON", "CONFIG_SNAPSHOT", "SECURITY_AUDIT"
    };
    int idx = static_cast<int>(layer);
    return (idx >= 0 && idx < 8) ? names[idx] : "UNKNOWN";
}

inline const char* component_type_to_string(ComponentType type) {
    static const char* names[] = {
        "UNKNOWN", "SERVICE", "DATABASE", "CACHE", "MESSAGE_QUEUE",
        "GATEWAY", "LOAD_BALANCER", "PROXY", "SIDECAR"
    };
    int idx = static_cast<int>(type);
    return (idx >= 0 && idx < 9) ? names[idx] : "UNKNOWN";
}

inline const char* decay_type_to_string(DecayType type) {
    static const char* names[] = {
        "EXPONENTIAL", "GAMMA", "BI_EXPONENTIAL", "POWER_LAW", "STRETCHED_EXP"
    };
    int idx = static_cast<int>(type);
    return (idx >= 0 && idx < 5) ? names[idx] : "UNKNOWN";
}

inline const char* normalization_type_to_string(NormalizationType type) {
    static const char* names[] = {
        "NONE", "L1_NORM", "L2_NORM", "MAX_NORM", "CAUSAL_CONE"
    };
    int idx = static_cast<int>(type);
    return (idx >= 0 && idx < 5) ? names[idx] : "UNKNOWN";
}

// Kernels per component per layer
constexpr int KERNELS_PER_COMPONENT = static_cast<int>(BoundaryLayer::COUNT);

} // namespace cauveris