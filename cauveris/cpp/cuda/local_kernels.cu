#include "cauveris/kernel_types.h"
#include <cmath>

namespace cauveris {

__global__ void build_local_kernels_kernel(
    const int* component_indices,
    const int* layer_indices,
    float* tau_ns,
    float* peak_time_ns,
    float* half_life_ns,
    float* integral,
    float* kernel_values,
    const float* time_axis_ns,
    int num_kernels,
    int max_time_steps,
    int decay_type,
    int normalization
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= num_kernels) return;

    int layer = layer_indices[idx];

    // Compute tau based on layer (simplified - in practice would use component type too)
    float base_tau_ms = 10.0f;

    switch (static_cast<BoundaryLayer>(layer)) {
        case BoundaryLayer::APPLICATION_LOG: base_tau_ms *= 1.0f; break;
        case BoundaryLayer::METRICS_EXPORT: base_tau_ms *= 5.0f; break;
        case BoundaryLayer::DISTRIBUTED_TRACE: base_tau_ms *= 0.3f; break;
        case BoundaryLayer::NETWORK_FLOW: base_tau_ms *= 1.0f; break;
        case BoundaryLayer::INFRASTRUCTURE_LOG: base_tau_ms *= 1.2f; break;
        case BoundaryLayer::CONFIG_STATE: base_tau_ms *= 10.0f; break;
        case BoundaryLayer::DEPLOYMENT_EVENT: base_tau_ms *= 0.1f; break;
        default: break;
    }

    float tau = base_tau_ms * 1'000'000.0f; // nanoseconds
    tau_ns[idx] = tau;

    // Generate kernel values
    float* kernel = kernel_values + idx * max_time_steps;

    switch (static_cast<DecayType>(decay_type)) {
        case DecayType::EXPONENTIAL: {
            for (int i = 0; i < max_time_steps; ++i) {
                float t = time_axis_ns[i];
                kernel[i] = expf(-t / tau) / tau;
            }
            break;
        }
        case DecayType::GAMMA: {
            float shape = 2.0f;
            float scale = tau / shape;
            for (int i = 0; i < max_time_steps; ++i) {
                float t = time_axis_ns[i];
                if (t > 0) {
                    kernel[i] = powf(t, shape - 1.0f) * expf(-t / scale) /
                               (powf(scale, shape) * tgammaf(shape));
                } else {
                    kernel[i] = 0.0f;
                }
            }
            break;
        }
        case DecayType::BI_EXPONENTIAL: {
            float tau_fast = tau * 0.1f;
            float tau_slow = tau;
            for (int i = 0; i < max_time_steps; ++i) {
                float t = time_axis_ns[i];
                kernel[i] = 0.7f * expf(-t / tau_fast) / tau_fast +
                           0.3f * expf(-t / tau_slow) / tau_slow;
            }
            break;
        }
    }

    // Normalize
    float dt = time_axis_ns[1] - time_axis_ns[0];
    float norm_factor = 1.0f;

    if (static_cast<NormalizationType>(normalization) == NormalizationType::L1) {
        float sum = 0.0f;
        for (int i = 1; i < max_time_steps; ++i) {
            sum += 0.5f * (kernel[i] + kernel[i - 1]) * dt;
        }
        if (sum > 0.0f) norm_factor = 1.0f / sum;
    } else if (static_cast<NormalizationType>(normalization) == NormalizationType::L2) {
        float sum = 0.0f;
        for (int i = 1; i < max_time_steps; ++i) {
            sum += 0.5f * (kernel[i] * kernel[i] + kernel[i - 1] * kernel[i - 1]) * dt;
        }
        sum = sqrtf(sum);
        if (sum > 0.0f) norm_factor = 1.0f / sum;
    } else if (static_cast<NormalizationType>(normalization) == NormalizationType::MAX) {
        float max_val = 0.0f;
        for (int i = 0; i < max_time_steps; ++i) {
            if (kernel[i] > max_val) max_val = kernel[i];
        }
        if (max_val > 0.0f) norm_factor = 1.0f / max_val;
    }

    for (int i = 0; i < max_time_steps; ++i) {
        kernel[i] *= norm_factor;
    }

    // Compute peak time
    float max_val = 0.0f;
    int peak_idx = 0;
    for (int i = 0; i < max_time_steps; ++i) {
        if (kernel[i] > max_val) {
            max_val = kernel[i];
            peak_idx = i;
        }
    }
    peak_time_ns[idx] = time_axis_ns[peak_idx];

    // Compute half-life
    float half_val = max_val * 0.5f;
    for (int i = peak_idx; i < max_time_steps; ++i) {
        if (kernel[i] <= half_val) {
            half_life_ns[idx] = time_axis_ns[i];
            break;
        }
    }
    if (half_life_ns[idx] == 0.0f) {
        half_life_ns[idx] = time_axis_ns[max_time_steps - 1];
    }

    // Compute integral
    float integ = 0.0f;
    for (int i = 1; i < max_time_steps; ++i) {
        integ += 0.5f * (kernel[i] + kernel[i - 1]) * dt;
    }
    integral[idx] = integ;
}

__global__ void evaluate_local_kernels_kernel(
    const float* kernel_values,
    const float* time_axis_ns,
    const int* component_indices,
    const int* layer_indices,
    const float* query_times_ns,
    float* results,
    int num_kernels,
    int max_time_steps,
    int num_queries
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= num_kernels * num_queries) return;

    int kernel_idx = idx / num_queries;
    int query_idx = idx % num_queries;

    float t = query_times_ns[query_idx];
    const float* kernel = kernel_values + kernel_idx * max_time_steps;

    if (t < 0.0f || t >= time_axis_ns[max_time_steps - 1]) {
        results[idx] = 0.0f;
        return;
    }

    float dt = time_axis_ns[1] - time_axis_ns[0];
    int time_idx = static_cast<int>(t / dt);
    results[idx] = kernel[time_idx];
}

} // namespace cauveris