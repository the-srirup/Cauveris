#pragma once

#include <cuda_runtime.h>
#include <cstdint>
#include <vector>
#include <string>
#include <memory>

namespace cauveris {

// Forward declarations
struct LocalPropagationKernel;
struct CrossPropagationKernel;
struct KernelConfig;
struct KernelMatrix;
struct ConvolutionResult;
struct SolverResult;

// Enums
enum class BoundaryLayer : uint8_t {
    APPLICATION_LOG = 0,
    METRICS_EXPORT = 1,
    DISTRIBUTED_TRACE = 2,
    NETWORK_FLOW = 3,
    INFRASTRUCTURE_LOG = 4,
    CONFIG_STATE = 5,
    DEPLOYMENT_EVENT = 6,
    COUNT = 7
};

enum class ComponentType : uint8_t {
    SERVICE = 0,
    DATABASE = 1,
    CACHE = 2,
    GATEWAY = 3,
    MESSAGE_QUEUE = 4,
    MONITORING = 5,
    COUNT = 6
};

enum class DecayType : uint8_t {
    EXPONENTIAL = 0,
    GAMMA = 1,
    BI_EXPONENTIAL = 2
};

enum class NormalizationType : uint8_t {
    L1 = 0,
    L2 = 1,
    MAX = 2
};

// Configuration structures
struct KernelConfig {
    int64_t time_step_ns = 1'000'000;          // 1ms resolution
    int64_t max_kernel_time_ns = 10'000'000'000; // 10 second max propagation
    float self_latency_factor = 0.1f;
    float queue_service_time_ms = 0.5f;
    DecayType decay_type = DecayType::EXPONENTIAL;
    NormalizationType normalization = NormalizationType::L1;
};

// Kernel data structures
struct LocalPropagationKernel {
    std::string component_name;
    BoundaryLayer boundary_layer;
    std::vector<float> time_axis_ns;
    std::vector<float> kernel_values;
    float integral = 0.0f;
    float peak_time_ns = 0.0f;
    float half_life_ns = 0.0f;

    __host__ __device__ float evaluate_at(float t_ns) const {
        if (t_ns < 0.0f || t_ns >= time_axis_ns.back()) return 0.0f;
        float dt = time_axis_ns[1] - time_axis_ns[0];
        int idx = static_cast<int>(t_ns / dt);
        return kernel_values[idx];
    }
};

struct CrossPropagationKernel {
    std::string source;
    std::string target;
    std::string edge_type;
    std::vector<float> time_axis_ns;
    std::vector<float> kernel_values;
    float total_latency_ns = 0.0f;
    float network_latency_ns = 0.0f;
    float queueing_latency_ns = 0.0f;
};

// High-performance GPU structures (SOA layout)
struct LocalKernelsGPU {
    // Per-kernel metadata (compact)
    int num_kernels = 0;
    int max_time_steps = 0;

    // Component indices
    int* component_indices = nullptr;     // [num_kernels]
    int* layer_indices = nullptr;         // [num_kernels]

    // Kernel parameters
    float* tau_ns = nullptr;              // [num_kernels] - time constant
    float* peak_time_ns = nullptr;        // [num_kernels]
    float* half_life_ns = nullptr;        // [num_kernels]
    float* integral = nullptr;            // [num_kernels]

    // Kernel values (flattened: [num_kernels * max_time_steps])
    float* kernel_values = nullptr;

    // Time axis (shared)
    float* time_axis_ns = nullptr;        // [max_time_steps]
};

struct CrossKernelsGPU {
    int num_kernels = 0;
    int max_time_steps = 0;

    // Source/target indices
    int* source_indices = nullptr;        // [num_kernels]
    int* target_indices = nullptr;        // [num_kernels]
    int* edge_type_indices = nullptr;     // [num_kernels]

    // Kernel parameters
    float* tau_ns = nullptr;              // [num_kernels]
    float* total_latency_ns = nullptr;    // [num_kernels]
    float* network_latency_ns = nullptr;  // [num_kernels]
    float* queueing_latency_ns = nullptr; // [num_kernels]

    // Kernel values (flattened)
    float* kernel_values = nullptr;

    // Time axis (shared)
    float* time_axis_ns = nullptr;        // [max_time_steps]
};

// Kernel Matrix for measurement system
struct KernelMatrix {
    int num_components = 0;
    int num_layers = 0;
    int num_time_steps = 0;

    // K[obs_idx, comp_idx, time_idx] flattened to [num_obs * num_comp * num_time_steps]
    // obs_idx = comp_idx * num_layers + layer_idx
    float* data = nullptr;

    // Source component index for each observation
    int* obs_to_component = nullptr;      // [num_obs]
    int* obs_to_layer = nullptr;          // [num_obs]
};

// Convolution result
struct ConvolutionResult {
    std::vector<float> output;
    float peak_value = 0.0f;
    float peak_time_ns = 0.0f;
    float integral = 0.0f;
};

// Solver configuration
struct SolverConfig {
    int max_iterations = 1000;
    float tolerance = 1e-6f;
    float regularization = 1e-4f;
    bool use_gpu = true;
    int gpu_device_id = 0;
};

// Solver result
struct SolverResult {
    std::vector<float> reconstructed_state;
    std::vector<float> residuals;
    int iterations = 0;
    float final_residual = 0.0f;
    bool converged = false;
    float solve_time_ms = 0.0f;
};

// Memory management helpers
class CudaMemoryManager {
public:
    static void* allocate(size_t bytes);
    static void free(void* ptr);
    static void copy_host_to_device(void* dst, const void* src, size_t bytes);
    static void copy_device_to_host(void* dst, const void* src, size_t bytes);
    static void copy_device_to_device(void* dst, const void* src, size_t bytes);
    static void memset(void* ptr, int value, size_t bytes);
};

// Error checking
#define CAUVERIS_CUDA_CHECK(call) \
    do { \
        cudaError_t err = call; \
        if (err != cudaSuccess) { \
            fprintf(stderr, "CUDA error at %s:%d - %s\n", __FILE__, __LINE__, cudaGetErrorString(err)); \
            throw std::runtime_error("CUDA error: " + std::string(cudaGetErrorString(err))); \
        } \
    } while(0)

// Kernel launch configuration
struct LaunchConfig {
    int block_size = 256;
    int grid_size = 1;

    static LaunchConfig for_size(int num_elements, int block_size = 256) {
        LaunchConfig cfg;
        cfg.block_size = block_size;
        cfg.grid_size = (num_elements + block_size - 1) / block_size;
        return cfg;
    }
};

} // namespace cauveris