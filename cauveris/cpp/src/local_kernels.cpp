#include "cauveris/local_kernels.h"
#include "cauveris/kernel_types.h"
#include <cmath>
#include <algorithm>
#include <stdexcept>

namespace cauveris {

LocalKernelBuilder::LocalKernelBuilder(const KernelConfig& config) : config_(config) {}

std::unordered_map<std::string, LocalPropagationKernel> LocalKernelBuilder::build_kernels(
    const std::vector<std::string>& component_names,
    const std::vector<ComponentType>& component_types,
    const std::vector<std::vector<BoundaryLayer>>& component_layers
) {
    std::unordered_map<std::string, LocalPropagationKernel> kernels;

    for (size_t i = 0; i < component_names.size(); ++i) {
        const auto& name = component_names[i];
        const auto type = component_types[i];
        const auto& layers = component_layers[i];

        for (const auto layer : layers) {
            std::string key = name + "|" + std::to_string(static_cast<int>(layer));
            kernels[key] = build_kernel(name, type, layer);
        }
    }

    return kernels;
}

LocalPropagationKernel LocalKernelBuilder::build_kernel(
    const std::string& component_name,
    ComponentType component_type,
    BoundaryLayer layer
) {
    auto time_axis = generate_time_axis();
    float tau_ns = compute_tau_ns(component_type, layer);
    auto kernel_values = generate_kernel_values(tau_ns, time_axis);

    normalize_kernel(kernel_values, time_axis);

    float integral = compute_integral(kernel_values, time_axis);
    float peak_time = compute_peak_time(kernel_values, time_axis);
    float half_life = compute_half_life(kernel_values, time_axis);

    LocalPropagationKernel kernel;
    kernel.component_name = component_name;
    kernel.boundary_layer = layer;
    kernel.time_axis_ns = std::move(time_axis);
    kernel.kernel_values = std::move(kernel_values);
    kernel.integral = integral;
    kernel.peak_time_ns = peak_time;
    kernel.half_life_ns = half_life;

    return kernel;
}

LocalKernelsGPU LocalKernelBuilder::upload_to_gpu(
    const std::unordered_map<std::string, LocalPropagationKernel>& kernels
) {
    LocalKernelsGPU gpu;
    gpu.num_kernels = static_cast<int>(kernels.size());

    // Find max time steps
    gpu.max_time_steps = 0;
    for (const auto& [key, kernel] : kernels) {
        gpu.max_time_steps = std::max(gpu.max_time_steps, static_cast<int>(kernel.time_axis_ns.size()));
    }

    // Allocate GPU memory
    size_t num_kernels = gpu.num_kernels;
    size_t max_steps = gpu.max_time_steps;

    gpu.component_indices = static_cast<int*>(CudaMemoryManager::allocate(num_kernels * sizeof(int)));
    gpu.layer_indices = static_cast<int*>(CudaMemoryManager::allocate(num_kernels * sizeof(int)));
    gpu.tau_ns = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * sizeof(float)));
    gpu.peak_time_ns = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * sizeof(float)));
    gpu.half_life_ns = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * sizeof(float)));
    gpu.integral = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * sizeof(float)));
    gpu.kernel_values = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * max_steps * sizeof(float)));
    gpu.time_axis_ns = static_cast<float*>(CudaMemoryManager::allocate(max_steps * sizeof(float)));

    // Prepare host buffers
    std::vector<int> h_component_indices(num_kernels);
    std::vector<int> h_layer_indices(num_kernels);
    std::vector<float> h_tau_ns(num_kernels);
    std::vector<float> h_peak_time(num_kernels);
    std::vector<float> h_half_life(num_kernels);
    std::vector<float> h_integral(num_kernels);
    std::vector<float> h_kernel_values(num_kernels * max_steps, 0.0f);
    std::vector<float> h_time_axis(max_steps);

    // Copy time axis (use first kernel's time axis, they should all be the same)
    size_t idx = 0;
    for (const auto& [key, kernel] : kernels) {
        if (idx == 0) {
            std::copy(kernel.time_axis_ns.begin(), kernel.time_axis_ns.end(), h_time_axis.begin());
        }
        ++idx;
    }

    // Copy kernel data
    idx = 0;
    for (const auto& [key, kernel] : kernels) {
        // Parse component index from key (simplified: use hash)
        h_component_indices[idx] = static_cast<int>(std::hash<std::string>{}(kernel.component_name) % 10000);
        h_layer_indices[idx] = static_cast<int>(kernel.boundary_layer);
        h_tau_ns[idx] = compute_tau_ns(ComponentType::SERVICE, kernel.boundary_layer); // Simplified
        h_peak_time[idx] = kernel.peak_time_ns;
        h_half_life[idx] = kernel.half_life_ns;
        h_integral[idx] = kernel.integral;

        // Copy kernel values (pad with zeros if needed)
        size_t copy_size = std::min(kernel.kernel_values.size(), static_cast<size_t>(max_steps));
        std::copy(kernel.kernel_values.begin(), kernel.kernel_values.begin() + copy_size,
                  h_kernel_values.begin() + idx * max_steps);

        ++idx;
    }

    // Upload to GPU
    CudaMemoryManager::copy_host_to_device(gpu.component_indices, h_component_indices.data(), num_kernels * sizeof(int));
    CudaMemoryManager::copy_host_to_device(gpu.layer_indices, h_layer_indices.data(), num_kernels * sizeof(int));
    CudaMemoryManager::copy_host_to_device(gpu.tau_ns, h_tau_ns.data(), num_kernels * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.peak_time_ns, h_peak_time.data(), num_kernels * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.half_life_ns, h_half_life.data(), num_kernels * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.integral, h_integral.data(), num_kernels * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.kernel_values, h_kernel_values.data(), num_kernels * max_steps * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.time_axis_ns, h_time_axis.data(), max_steps * sizeof(float));

    return gpu;
}

std::unordered_map<std::string, LocalPropagationKernel> LocalKernelBuilder::download_from_gpu(
    const LocalKernelsGPU& gpu_kernels
) {
    std::unordered_map<std::string, LocalPropagationKernel> kernels;

    // This is a simplified download - in practice you'd need to keep track of the component names
    // For now, we'll just return empty as this is mainly for verification
    return kernels;
}

float LocalKernelBuilder::compute_tau_ns(ComponentType type, BoundaryLayer layer) const {
    float base_tau_ms = 10.0f;

    // Component type factors
    switch (type) {
        case ComponentType::SERVICE: base_tau_ms *= 1.0f; break;
        case ComponentType::DATABASE: base_tau_ms *= 2.0f; break;
        case ComponentType::CACHE: base_tau_ms *= 0.5f; break;
        case ComponentType::GATEWAY: base_tau_ms *= 0.8f; break;
        case ComponentType::MESSAGE_QUEUE: base_tau_ms *= 0.5f; break;
        case ComponentType::MONITORING: base_tau_ms *= 1.5f; break;
    }

    // Layer factors
    switch (layer) {
        case BoundaryLayer::APPLICATION_LOG: base_tau_ms *= 1.0f; break;
        case BoundaryLayer::METRICS_EXPORT: base_tau_ms *= 5.0f; break;
        case BoundaryLayer::DISTRIBUTED_TRACE: base_tau_ms *= 0.3f; break;
        case BoundaryLayer::NETWORK_FLOW: base_tau_ms *= 1.0f; break;
        case BoundaryLayer::INFRASTRUCTURE_LOG: base_tau_ms *= 1.2f; break;
        case BoundaryLayer::CONFIG_STATE: base_tau_ms *= 10.0f; break;
        case BoundaryLayer::DEPLOYMENT_EVENT: base_tau_ms *= 0.1f; break;
        default: break;
    }

    return base_tau_ms * 1'000'000.0f; // Convert to nanoseconds
}

std::vector<float> LocalKernelBuilder::generate_time_axis() const {
    int num_steps = static_cast<int>(config_.max_kernel_time_ns / config_.time_step_ns);
    std::vector<float> time_axis(num_steps);
    for (int i = 0; i < num_steps; ++i) {
        time_axis[i] = i * config_.time_step_ns;
    }
    return time_axis;
}

std::vector<float> LocalKernelBuilder::generate_kernel_values(float tau_ns, const std::vector<float>& time_axis) const {
    std::vector<float> kernel(time_axis.size());

    switch (config_.decay_type) {
        case DecayType::EXPONENTIAL: {
            for (size_t i = 0; i < time_axis.size(); ++i) {
                kernel[i] = std::exp(-time_axis[i] / tau_ns) / tau_ns;
            }
            break;
        }
        case DecayType::GAMMA: {
            float shape = 2.0f;
            float scale = tau_ns / shape;
            for (size_t i = 0; i < time_axis.size(); ++i) {
                float t = time_axis[i];
                if (t > 0) {
                    kernel[i] = std::pow(t, shape - 1.0f) * std::exp(-t / scale) /
                               (std::pow(scale, shape) * std::tgamma(shape));
                } else {
                    kernel[i] = 0.0f;
                }
            }
            break;
        }
        case DecayType::BI_EXPONENTIAL: {
            float tau_fast = tau_ns * 0.1f;
            float tau_slow = tau_ns;
            for (size_t i = 0; i < time_axis.size(); ++i) {
                float t = time_axis[i];
                kernel[i] = 0.7f * std::exp(-t / tau_fast) / tau_fast +
                           0.3f * std::exp(-t / tau_slow) / tau_slow;
            }
            break;
        }
    }

    return kernel;
}

float LocalKernelBuilder::compute_integral(const std::vector<float>& kernel, const std::vector<float>& time_axis) const {
    float integral = 0.0f;
    for (size_t i = 1; i < kernel.size(); ++i) {
        float dt = time_axis[i] - time_axis[i - 1];
        integral += 0.5f * (kernel[i] + kernel[i - 1]) * dt;
    }
    return integral;
}

float LocalKernelBuilder::compute_peak_time(const std::vector<float>& kernel, const std::vector<float>& time_axis) const {
    auto max_it = std::max_element(kernel.begin(), kernel.end());
    size_t idx = std::distance(kernel.begin(), max_it);
    return time_axis[idx];
}

float LocalKernelBuilder::compute_half_life(const std::vector<float>& kernel, const std::vector<float>& time_axis) const {
    auto max_it = std::max_element(kernel.begin(), kernel.end());
    size_t peak_idx = std::distance(kernel.begin(), max_it);
    float peak_val = *max_it;

    for (size_t i = peak_idx; i < kernel.size(); ++i) {
        if (kernel[i] <= peak_val * 0.5f) {
            return time_axis[i];
        }
    }
    return time_axis.back();
}

void LocalKernelBuilder::normalize_kernel(std::vector<float>& kernel, const std::vector<float>& time_axis) const {
    float factor = 1.0f;

    switch (config_.normalization) {
        case NormalizationType::L1: {
            float integral = compute_integral(kernel, time_axis);
            if (integral > 0.0f) factor = 1.0f / integral;
            break;
        }
        case NormalizationType::L2: {
            float norm = 0.0f;
            for (size_t i = 1; i < kernel.size(); ++i) {
                float dt = time_axis[i] - time_axis[i - 1];
                norm += 0.5f * (kernel[i] * kernel[i] + kernel[i - 1] * kernel[i - 1]) * dt;
            }
            norm = std::sqrt(norm);
            if (norm > 0.0f) factor = 1.0f / norm;
            break;
        }
        case NormalizationType::MAX: {
            float max_val = *std::max_element(kernel.begin(), kernel.end());
            if (max_val > 0.0f) factor = 1.0f / max_val;
            break;
        }
    }

    for (auto& val : kernel) {
        val *= factor;
    }
}

} // namespace cauveris