/**
 * CUDA Kernels for Local Propagation Kernel Construction.
 *
 * Implements high-performance GPU kernels for building per-component,
 * per-boundary-layer propagation kernels with multiple decay functions.
 */

#include "cauveris/local_kernels.h"
#include "cauveris/kernel_types.h"
#include <cuda_runtime.h>
#include <cuda_fp16.h>
#include <math.h>
#include <cstdio>

namespace cauveris {

// ============================================================================
// Device Functions for Decay Computation
// ============================================================================

__device__ __host__ float compute_decay_value(float t, DecayType type, const float* params) {
    switch (type) {
        case DecayType::EXPONENTIAL: {
            // exp(-λt)
            float lambda = params[0];
            return expf(-lambda * t);
        }
        case DecayType::GAMMA: {
            // t^(k-1) * exp(-t/θ) / (Γ(k) * θ^k)
            float k = params[0];
            float theta = params[1];
            if (t <= 0) return 0.0f;
            // Use lgamma for log gamma function
            float log_gamma_k = lgammaf(k);
            float log_val = (k - 1.0f) * logf(t) - t / theta - log_gamma_k - k * logf(theta);
            return expf(log_val);
        }
        case DecayType::BI_EXPONENTIAL: {
            // a * exp(-λ₁t) + (1-a) * exp(-λ₂t)
            float a = params[0];
            float lambda1 = params[1];
            float lambda2 = params[2];
            return a * expf(-lambda1 * t) + (1.0f - a) * expf(-lambda2 * t);
        }
        case DecayType::POWER_LAW: {
            // t^(-α) for t > 0
            float alpha = params[0];
            if (t <= 0) return 1.0f;  // Avoid singularity at t=0
            return powf(t, -alpha);
        }
        case DecayType::STRETCHED_EXP: {
            // exp(-(t/τ)^β)
            float tau = params[0];
            float beta = params[1];
            if (t <= 0) return 1.0f;
            return expf(-powf(t / tau, beta));
        }
        default:
            return expf(-params[0] * t);  // Default to exponential
    }
}

__device__ __host__ float compute_decay_integral(float t_max, DecayType type, const float* params) {
    // Analytical integrals for normalization
    switch (type) {
        case DecayType::EXPONENTIAL: {
            float lambda = params[0];
            return (1.0f - expf(-lambda * t_max)) / lambda;
        }
        case DecayType::GAMMA: {
            // No simple closed form, approximate numerically
            float k = params[0];
            float theta = params[1];
            // Use incomplete gamma function approximation
            return t_max * 0.5f;  // Simplified
        }
        case DecayType::BI_EXPONENTIAL: {
            float a = params[0];
            float lambda1 = params[1];
            float lambda2 = params[2];
            return a * (1.0f - expf(-lambda1 * t_max)) / lambda1 +
                   (1.0f - a) * (1.0f - expf(-lambda2 * t_max)) / lambda2;
        }
        case DecayType::POWER_LAW: {
            float alpha = params[0];
            if (alpha == 1.0f) return logf(t_max + 1.0f);
            return (powf(t_max, 1.0f - alpha) - 1.0f) / (1.0f - alpha);
        }
        case DecayType::STRETCHED_EXP: {
            float tau = params[0];
            float beta = params[1];
            // Approximate with tau * Γ(1/β) / β
            return tau * tgammaf(1.0f / beta) / beta;
        }
        default:
            return 1.0f;
    }
}

// ============================================================================
// Kernel: Build Local Propagation Kernels
// ============================================================================

__global__ void build_local_kernels_kernel(
    LocalKernelsGPU gpu_kernels,
    const int* component_ids,
    const ComponentType* component_types,
    const float* component_decay_rates,
    const float* layer_weights,
    int num_components,
    int num_layers,
    int time_steps,
    float time_step_ns
) {
    // Each thread handles one (component, layer) pair
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total_pairs = num_components * num_layers;

    if (idx >= total_pairs) return;

    int comp = idx / num_layers;
    int layer = idx % num_layers;

    // Get component type and decay rate
    ComponentType comp_type = component_types[comp];
    float decay_rate = component_decay_rates[static_cast<int>(comp_type)];
    float layer_weight = layer_weights[layer];

    // Get kernel pointer
    float* kernel = gpu_kernels.get_kernel_ptr(0, comp, layer);
    if (!kernel) return;

    // Default decay parameters
    float params[4] = {decay_rate, 0.0f, 0.0f, 0.0f};
    DecayType decay_type = DecayType::EXPONENTIAL;

    // Compute unnormalized kernel and sum for normalization
    float sum = 0.0f;
    for (int t = 0; t < time_steps; ++t) {
        float time_ns = t * time_step_ns;
        float val = compute_decay_value(time_ns, decay_type, params);
        sum += val;
    }

    // Normalize
    float norm_factor = (sum > 0) ? (1.0f / sum) : 1.0f;
    gpu_kernels.normalization_factors[comp * num_layers + layer] = norm_factor * layer_weight;

    // Write normalized kernel
    for (int t = 0; t < time_steps; ++t) {
        float time_ns = t * time_step_ns;
        float val = compute_decay_value(time_ns, decay_type, params);
        kernel[t] = val * norm_factor * layer_weight;
    }
}

__global__ void build_local_kernels_advanced_kernel(
    LocalKernelsGPU gpu_kernels,
    const int* component_ids,
    const ComponentType* component_types,
    const uint8_t* decay_types,
    const float* decay_params,
    const float* layer_weights,
    int num_components,
    int num_layers,
    int time_steps,
    float time_step_ns
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total_pairs = num_components * num_layers;

    if (idx >= total_pairs) return;

    int comp = idx / num_layers;
    int layer = idx % num_layers;

    // Per component-layer decay type and params
    int param_idx = (comp * num_layers + layer) * 4;
    DecayType decay_type = static_cast<DecayType>(decay_types[comp * num_layers + layer]);
    float params[4] = {
        decay_params[param_idx],
        decay_params[param_idx + 1],
        decay_params[param_idx + 2],
        decay_params[param_idx + 3]
    };
    float layer_weight = layer_weights[layer];

    float* kernel = gpu_kernels.get_kernel_ptr(0, comp, layer);
    if (!kernel) return;

    // Compute sum for normalization
    float sum = 0.0f;
    for (int t = 0; t < time_steps; ++t) {
        float time_ns = t * time_step_ns;
        sum += compute_decay_value(time_ns, decay_type, params);
    }

    float norm_factor = (sum > 0) ? (1.0f / sum) : 1.0f;
    gpu_kernels.normalization_factors[comp * num_layers + layer] = norm_factor * layer_weight;

    for (int t = 0; t < time_steps; ++t) {
        float time_ns = t * time_step_ns;
        float val = compute_decay_value(time_ns, decay_type, params);
        kernel[t] = val * norm_factor * layer_weight;
    }
}

// ============================================================================
// Kernel: Causal Cone Truncation
// ============================================================================

__global__ void apply_causal_cone_kernel(
    LocalKernelsGPU gpu_kernels,
    const float* causal_distances,
    int num_components,
    int num_layers,
    int time_steps,
    float time_step_ns,
    float max_causal_speed  // units per ns
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total_pairs = num_components * num_layers;

    if (idx >= total_pairs) return;

    int comp = idx / num_layers;
    int layer = idx % num_layers;

    float* kernel = gpu_kernels.get_kernel_ptr(0, comp, layer);
    if (!kernel) return;

    // Zero out values beyond causal cone
    for (int t = 0; t < time_steps; ++t) {
        float time_ns = t * time_step_ns;
        float max_dist = max_causal_speed * time_ns;
        // If distance to any other component exceeds causal cone, this could be used
        // For now, just apply a temporal causal cone (minimum time for light to travel)
        if (t * time_step_ns < 1.0f) {  // Sub-ns precision
            kernel[t] = 0.0f;
        }
    }
}

// ============================================================================
// Kernel: Batched Convolution
// ============================================================================

__global__ void batched_convolution_kernel(
    const float* __restrict__ signal,      // [batch, components, layers, time]
    const float* __restrict__ kernel,      // [batch, components, layers, time]
    float* __restrict__ output,            // [batch, components, layers, time]
    int batch_size,
    int num_components,
    int num_layers,
    int signal_len,
    int kernel_len,
    int output_len
) {
    // 4D grid: batch, component, layer, output_time
    int b = blockIdx.z;
    int comp = blockIdx.y;
    int layer = blockIdx.x / gridDim.x;  // Simplified
    int t_out = blockIdx.x % gridDim.x + threadIdx.x * gridDim.x;

    if (b >= batch_size || comp >= num_components || layer >= num_layers || t_out >= output_len) return;

    int stride_batch = num_components * num_layers * signal_len;
    int stride_comp = num_layers * signal_len;
    int stride_layer = signal_len;

    int kernel_stride_batch = num_components * num_layers * kernel_len;
    int kernel_stride_comp = num_layers * kernel_len;
    int kernel_stride_layer = kernel_len;

    const float* sig_ptr = signal + b * stride_batch + comp * stride_comp + layer * stride_layer;
    const float* ker_ptr = kernel + b * kernel_stride_batch + comp * kernel_stride_comp + layer * kernel_stride_layer;
    float* out_ptr = output + b * stride_batch + comp * stride_comp + layer * stride_layer;

    float acc = 0.0f;
    for (int k = 0; k < kernel_len; ++k) {
        int t_in = t_out - k;
        if (t_in >= 0 && t_in < signal_len) {
            acc += sig_ptr[t_in] * ker_ptr[k];
        }
    }
    out_ptr[t_out] = acc;
}

// Optimized convolution using shared memory
__global__ void batched_convolution_shared_kernel(
    const float* __restrict__ signal,
    const float* __restrict__ kernel,
    float* __restrict__ output,
    int batch_size,
    int num_components,
    int num_layers,
    int signal_len,
    int kernel_len,
    int output_len
) {
    extern __shared__ float shared_mem[];
    float* sh_signal = shared_mem;
    float* sh_kernel = shared_mem + blockDim.x;

    int b = blockIdx.z;
    int comp = blockIdx.y;
    int layer = blockIdx.x;
    int tid = threadIdx.x;

    if (b >= batch_size || comp >= num_components || layer >= num_layers) return;

    int idx = b * num_components * num_layers + comp * num_layers + layer;

    // Load kernel into shared memory
    if (tid < kernel_len) {
        int ker_idx = idx * kernel_len + tid;
        sh_kernel[tid] = kernel[ker_idx];
    }
    __syncthreads();

    // Each thread computes one output element
    int t_out = tid;
    if (t_out >= output_len) return;

    // Load required signal segment into shared memory
    int t_start = max(0, t_out - kernel_len + 1);
    int t_end = min(t_out + 1, signal_len);
    int seg_len = t_end - t_start;

    if (tid < seg_len) {
        int sig_idx = idx * signal_len + t_start + tid;
        sh_signal[tid] = signal[sig_idx];
    }
    __syncthreads();

    float acc = 0.0f;
    for (int k = 0; k < kernel_len && (t_out - k) >= 0; ++k) {
        int sig_idx = t_out - k - t_start;
        if (sig_idx >= 0 && sig_idx < seg_len) {
            acc += sh_signal[sig_idx] * sh_kernel[k];
        }
    }

    int out_idx = idx * output_len + t_out;
    output[out_idx] = acc;
}

// ============================================================================
// Kernel: Cross-Correlation for Causal Discovery
// ============================================================================

__global__ void cross_correlation_kernel(
    const float* __restrict__ signal_a,    // [components, time]
    const float* __restrict__ signal_b,    // [components, time]
    float* __restrict__ correlation,       // [components, components, lags]
    int num_components,
    int signal_len,
    int max_lag
) {
    int src = blockIdx.y;
    int dst = blockIdx.x;
    int lag = threadIdx.x + blockIdx.z * blockDim.x;

    if (src >= num_components || dst >= num_components || lag > max_lag) return;

    // Skip self-correlation if not needed
    if (src == dst && lag == 0) return;

    const float* a = signal_a + src * signal_len;
    const float* b = signal_b + dst * signal_len;
    float* corr = correlation + (src * num_components + dst) * (max_lag + 1) + lag;

    float sum_ab = 0.0f;
    float sum_a2 = 0.0f;
    float sum_b2 = 0.0f;
    int count = 0;

    for (int t = 0; t < signal_len - lag; ++t) {
        float va = a[t + lag];
        float vb = b[t];
        sum_ab += va * vb;
        sum_a2 += va * va;
        sum_b2 += vb * vb;
        count++;
    }

    if (count > 0) {
        float denom = sqrtf(sum_a2 * sum_b2);
        *corr = (denom > 0) ? sum_ab / denom : 0.0f;
    } else {
        *corr = 0.0f;
    }
}

// ============================================================================
// Kernel: Kernel Matrix Entries (K_ij = ∫ K_i(t) * K_j(t) dt)
// ============================================================================

__global__ void kernel_matrix_entries_kernel(
    const LocalKernelsGPU gpu_kernels,
    float* matrix,              // [components, components]
    int num_components,
    int num_layers,
    int time_steps
) {
    int src = blockIdx.y;
    int dst = blockIdx.x;

    if (src >= num_components || dst >= num_components) return;

    // Compute kernel overlap across all layers
    float sum = 0.0f;
    for (int layer = 0; layer < num_layers; ++layer) {
        const float* k_src = gpu_kernels.get_kernel_ptr(0, src, layer);
        const float* k_dst = gpu_kernels.get_kernel_ptr(0, dst, layer);

        if (!k_src || !k_dst) continue;

        for (int t = 0; t < time_steps; ++t) {
            sum += k_src[t] * k_dst[t];
        }
    }

    // Weight by normalization factors
    float norm_src = 1.0f;
    float norm_dst = 1.0f;
    for (int layer = 0; layer < num_layers; ++layer) {
        norm_src *= gpu_kernels.get_normalization(0, src, layer);
        norm_dst *= gpu_kernels.get_normalization(0, dst, layer);
    }

    matrix[src * num_components + dst] = sum * sqrtf(norm_src * norm_dst);
}

// ============================================================================
// Host Launch Functions
// ============================================================================

void launch_build_local_kernels(LocalKernelsGPU& gpu_kernels,
                                const int* component_ids,
                                const ComponentType* component_types,
                                int num_components,
                                int batch_size,
                                const KernelConfig& config) {
    int total_pairs = num_components * static_cast<int>(BoundaryLayer::COUNT);
    int threads = 256;
    int blocks = (total_pairs + threads - 1) / threads;

    // Allocate device arrays for component data
    int* d_component_ids;
    ComponentType* d_component_types;
    cudaMalloc(&d_component_ids, num_components * sizeof(int));
    cudaMalloc(&d_component_types, num_components * sizeof(ComponentType));
    cudaMemcpy(d_component_ids, component_ids, num_components * sizeof(int), cudaMemcpyHostToDevice);
    cudaMemcpy(d_component_types, component_types, num_components * sizeof(ComponentType), cudaMemcpyHostToDevice);

    // Component decay rates
    float h_decay_rates[static_cast<int>(ComponentType::COUNT)];
    for (int i = 0; i < static_cast<int>(ComponentType::COUNT); ++i) {
        h_decay_rates[i] = static_cast<float>(config.component_decay_rates[i]);
    }
    float* d_decay_rates;
    cudaMalloc(&d_decay_rates, static_cast<int>(ComponentType::COUNT) * sizeof(float));
    cudaMemcpy(d_decay_rates, h_decay_rates, static_cast<int>(ComponentType::COUNT) * sizeof(float), cudaMemcpyHostToDevice);

    // Layer weights
    float h_layer_weights[static_cast<int>(BoundaryLayer::COUNT)];
    for (int i = 0; i < static_cast<int>(BoundaryLayer::COUNT); ++i) {
        h_layer_weights[i] = static_cast<float>(config.layer_weights[i]);
    }
    float* d_layer_weights;
    cudaMalloc(&d_layer_weights, static_cast<int>(BoundaryLayer::COUNT) * sizeof(float));
    cudaMemcpy(d_layer_weights, h_layer_weights, static_cast<int>(BoundaryLayer::COUNT) * sizeof(float), cudaMemcpyHostToDevice);

    // Launch kernel
    build_local_kernels_kernel<<<blocks, threads>>>(
        gpu_kernels,
        d_component_ids,
        d_component_types,
        d_decay_rates,
        d_layer_weights,
        num_components,
        static_cast<int>(BoundaryLayer::COUNT),
        gpu_kernels.time_steps,
        static_cast<float>(config.time_step_ns)
    );

    cudaDeviceSynchronize();

    // Cleanup
    cudaFree(d_component_ids);
    cudaFree(d_component_types);
    cudaFree(d_decay_rates);
    cudaFree(d_layer_weights);
}

void launch_build_local_kernels_advanced(LocalKernelsGPU& gpu_kernels,
                                         const int* component_ids,
                                         const ComponentType* component_types,
                                         const uint8_t* decay_types,
                                         const float* decay_params,
                                         int num_components,
                                         const KernelConfig& config) {
    int total_pairs = num_components * static_cast<int>(BoundaryLayer::COUNT);
    int threads = 256;
    int blocks = (total_pairs + threads - 1) / threads;

    // Allocate device arrays
    int* d_component_ids;
    ComponentType* d_component_types;
    uint8_t* d_decay_types;
    float* d_decay_params;
    float* d_layer_weights;

    cudaMalloc(&d_component_ids, num_components * sizeof(int));
    cudaMalloc(&d_component_types, num_components * sizeof(ComponentType));
    cudaMalloc(&d_decay_types, total_pairs * sizeof(uint8_t));
    cudaMalloc(&d_decay_params, total_pairs * 4 * sizeof(float));
    cudaMalloc(&d_layer_weights, static_cast<int>(BoundaryLayer::COUNT) * sizeof(float));

    cudaMemcpy(d_component_ids, component_ids, num_components * sizeof(int), cudaMemcpyHostToDevice);
    cudaMemcpy(d_component_types, component_types, num_components * sizeof(ComponentType), cudaMemcpyHostToDevice);
    cudaMemcpy(d_decay_types, decay_types, total_pairs * sizeof(uint8_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_decay_params, decay_params, total_pairs * 4 * sizeof(float), cudaMemcpyHostToDevice);

    float h_layer_weights[static_cast<int>(BoundaryLayer::COUNT)];
    for (int i = 0; i < static_cast<int>(BoundaryLayer::COUNT); ++i) {
        h_layer_weights[i] = static_cast<float>(config.layer_weights[i]);
    }
    cudaMemcpy(d_layer_weights, h_layer_weights, static_cast<int>(BoundaryLayer::COUNT) * sizeof(float), cudaMemcpyHostToDevice);

    build_local_kernels_advanced_kernel<<<blocks, threads>>>(
        gpu_kernels,
        d_component_ids,
        d_component_types,
        d_decay_types,
        d_decay_params,
        d_layer_weights,
        num_components,
        static_cast<int>(BoundaryLayer::COUNT),
        gpu_kernels.time_steps,
        static_cast<float>(config.time_step_ns)
    );

    cudaDeviceSynchronize();

    cudaFree(d_component_ids);
    cudaFree(d_component_types);
    cudaFree(d_decay_types);
    cudaFree(d_decay_params);
    cudaFree(d_layer_weights);
}

void launch_batched_convolution(const float* signal,
                                const float* kernel,
                                float* output,
                                int batch_size,
                                int num_components,
                                int num_layers,
                                int signal_len,
                                int kernel_len,
                                int output_len) {
    dim3 grid(num_layers, num_components, batch_size);
    int threads = 256;

    size_t shared_mem = (kernel_len + signal_len) * sizeof(float);
    if (shared_mem > 48 * 1024) {
        // Fall back to non-shared version
        batched_convolution_kernel<<<grid, threads>>>(
            signal, kernel, output,
            batch_size, num_components, num_layers,
            signal_len, kernel_len, output_len
        );
    } else {
        batched_convolution_shared_kernel<<<grid, threads, shared_mem>>>(
            signal, kernel, output,
            batch_size, num_components, num_layers,
            signal_len, kernel_len, output_len
        );
    }
    cudaDeviceSynchronize();
}

void launch_cross_correlation(const float* signal_a,
                              const float* signal_b,
                              float* correlation,
                              int num_components,
                              int signal_len,
                              int max_lag) {
    dim3 grid(num_components, num_components, (max_lag + 255) / 256);
    int threads = 256;

    cross_correlation_kernel<<<grid, threads>>>(
        signal_a, signal_b, correlation,
        num_components, signal_len, max_lag
    );
    cudaDeviceSynchronize();
}

void launch_kernel_matrix_entries(const LocalKernelsGPU& gpu_kernels,
                                  float* matrix,
                                  int num_components) {
    dim3 grid(num_components, num_components);
    int threads = 1;

    kernel_matrix_entries_kernel<<<grid, threads>>>(
        gpu_kernels, matrix, num_components,
        static_cast<int>(BoundaryLayer::COUNT),
        gpu_kernels.time_steps
    );
    cudaDeviceSynchronize();
}

} // namespace cauveris