#include "cauveris/kernel_types.h"
#include <cmath>

namespace cauveris {

__global__ void convolve_kernels_kernel(
    const float* signal,
    const float* kernel,
    float* output,
    int signal_length,
    int kernel_length,
    float dt_ns
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= signal_length) return;

    float sum = 0.0f;
    int k_max = min(kernel_length, idx + 1);

    for (int k = 0; k < k_max; ++k) {
        sum += signal[idx - k] * kernel[k];
    }

    output[idx] = sum * (dt_ns / 1'000'000'000.0f);
}

__global__ void batch_convolve_kernel(
    const float* signals,      // [batch_size * signal_length]
    const float* kernels,      // [batch_size * kernel_length]
    float* outputs,            // [batch_size * signal_length]
    int batch_size,
    int signal_length,
    int kernel_length,
    float dt_ns
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total_elements = batch_size * signal_length;
    if (idx >= total_elements) return;

    int batch_idx = idx / signal_length;
    int signal_idx = idx % signal_length;

    const float* signal = signals + batch_idx * signal_length;
    const float* kernel = kernels + batch_idx * kernel_length;
    float* output = outputs + batch_idx * signal_length;

    float sum = 0.0f;
    int k_max = min(kernel_length, signal_idx + 1);

    for (int k = 0; k < k_max; ++k) {
        sum += signal[signal_idx - k] * kernel[k];
    }

    output[signal_idx] = sum * (dt_ns / 1'000'000'000.0f);
}

__global__ void batch_fft_convolve_kernel(
    const float* signals,
    const float* kernels,
    float* outputs,
    int batch_size,
    int signal_length,
    int kernel_length,
    float dt_ns
) {
    // This is a placeholder for FFT-based convolution
    // For production, use cuFFT library
    batch_convolve_kernel<<<gridDim.x, blockDim.x>>>(
        signals, kernels, outputs, batch_size, signal_length, kernel_length, dt_ns
    );
}

__global__ void compute_cross_correlation_kernel(
    const float* signal_a,
    const float* signal_b,
    float* correlation,
    int length,
    int max_lag
) {
    int lag = blockIdx.x * blockDim.x + threadIdx.x;
    if (lag > max_lag) return;

    float sum = 0.0f;
    int count = 0;
    for (int i = 0; i < length - lag; ++i) {
        sum += signal_a[i] * signal_b[i + lag];
        ++count;
    }
    correlation[lag] = (count > 0) ? sum / count : 0.0f;
}

__global__ void compute_kernel_matrix_entry_kernel(
    const float* src_kernel,
    const float* dst_kernel,
    float network_latency_ns,
    float queueing_latency_ns,
    float dt_ns,
    float* output,
    int num_steps
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= num_steps) return;

    float total_delay = network_latency_ns + queueing_latency_ns;
    int shift_idx = static_cast<int>(total_delay / dt_ns);

    if (shift_idx >= num_steps) {
        output[idx] = 0.0f;
        return;
    }

    // Convolve shifted src with dst
    float sum = 0.0f;
    int k_max = min(idx - shift_idx + 1, num_steps);
    if (k_max > 0) {
        for (int k = 0; k < k_max; ++k) {
            int src_idx = idx - shift_idx - k;
            if (src_idx >= 0 && src_idx < num_steps) {
                sum += src_kernel[src_idx] * dst_kernel[k];
            }
        }
    }

    output[idx] = sum * (dt_ns / 1'000'000'000.0f);
}

__global__ void build_full_kernel_matrix_kernel(
    const LocalKernelsGPU* local_kernels,
    const CrossKernelsGPU* cross_kernels,
    const int* component_indices,
    const int* layer_indices,
    const int* edges_src,
    const int* edges_dst,
    const float* edge_latencies,
    const int* edge_queue_depths,
    float* kernel_matrix,
    int num_components,
    int num_layers,
    int num_edges,
    int num_time_steps,
    int decay_type,
    int normalization
) {
    // This kernel builds the full K matrix: K[obs_idx, comp_idx, time_idx]
    // obs_idx = comp_idx * num_layers + layer_idx

    int obs_idx = blockIdx.x * blockDim.x + threadIdx.x;
    int num_obs = num_components * num_layers;
    if (obs_idx >= num_obs) return;

    int comp_idx = obs_idx / num_layers;
    int layer_idx = obs_idx % num_layers;

    // Local propagation (diagonal block)
    // Find the local kernel for this component+layer
    // This is a simplified placeholder - full implementation would search local_kernels

    // Cross propagation from all edges targeting this component
    for (int e = 0; e < num_edges; ++e) {
        if (edges_dst[e] == comp_idx) {
            int src_comp = edges_src[e];
            // Add cross-propagation contribution
            // ...
        }
    }
}

} // namespace cauveris