#include "cauveris/cross_kernels.h"
#include "cauveris/local_kernels.h"
#include "cauveris/kernel_types.h"
#include <algorithm>
#include <cmath>

namespace cauveris {

CrossKernelBuilder::CrossKernelBuilder(const KernelConfig& config) : config_(config) {}

std::unordered_map<std::string, CrossPropagationKernel> CrossKernelBuilder::build_kernels(
    const std::vector<std::string>& component_names,
    const std::vector<ComponentType>& component_types,
    const std::vector<std::vector<BoundaryLayer>>& component_layers,
    const std::vector<CausalEdge>& edges,
    const LocalKernelBuilder& local_builder
) {
    std::unordered_map<std::string, CrossPropagationKernel> kernels;

    for (const auto& edge : edges) {
        int src_idx = get_component_index(edge.source, component_names);
        int dst_idx = get_component_index(edge.target, component_names);

        if (src_idx < 0 || dst_idx < 0) continue;

        const auto& src_layers = component_layers[src_idx];
        const auto& dst_layers = component_layers[dst_idx];

        for (const auto src_layer : src_layers) {
            for (const auto dst_layer : dst_layers) {
                std::string key = edge.source + "|" + edge.target + "|" +
                                 std::to_string(static_cast<int>(src_layer)) + "|" +
                                 std::to_string(static_cast<int>(dst_layer));
                kernels[key] = build_kernel(edge.source, edge.target, edge, src_layer, dst_layer, local_builder);
            }
        }
    }

    return kernels;
}

CrossPropagationKernel CrossKernelBuilder::build_kernel(
    const std::string& source,
    const std::string& target,
    const CausalEdge& edge,
    BoundaryLayer src_layer,
    BoundaryLayer dst_layer,
    const LocalKernelBuilder& local_builder
) {
    // Get source and destination local kernels
    LocalPropagationKernel src_kernel = local_builder.build_kernel(source, ComponentType::SERVICE, src_layer);
    LocalPropagationKernel dst_kernel = local_builder.build_kernel(target, ComponentType::SERVICE, dst_layer);

    // Time axis (same as local kernels)
    auto time_axis = local_builder.generate_time_axis();
    int num_steps = static_cast<int>(time_axis.size());
    float dt_ns = config_.time_step_ns;

    // Network + queueing delay
    float network_latency_ns = edge.latency_ms * 1'000'000.0f;
    float queueing_latency_ns = edge.queue_depth * config_.queue_service_time_ms * 1'000'000.0f;
    float total_network_latency_ns = network_latency_ns + queueing_latency_ns;

    // Shift source kernel by network latency
    int shift_idx = static_cast<int>(total_network_latency_ns / dt_ns);
    std::vector<float> shifted_src(num_steps, 0.0f);
    if (shift_idx < num_steps) {
        int copy_size = std::min(static_cast<int>(src_kernel.kernel_values.size()), num_steps - shift_idx);
        std::copy(src_kernel.kernel_values.begin(),
                  src_kernel.kernel_values.begin() + copy_size,
                  shifted_src.begin() + shift_idx);
    }

    // Convolve: shifted_src * dst_kernel
    std::vector<float> cross_kernel(num_steps, 0.0f);
    for (int i = 0; i < num_steps; ++i) {
        float sum = 0.0f;
        int j_max = std::min(i + 1, static_cast<int>(dst_kernel.kernel_values.size()));
        for (int j = 0; j < j_max; ++j) {
            sum += shifted_src[i - j] * dst_kernel.kernel_values[j];
        }
        cross_kernel[i] = sum * (dt_ns / 1'000'000'000.0f); // Convert ns to seconds for integration
    }

    // Normalize
    if (config_.normalization == NormalizationType::L1) {
        float integral = 0.0f;
        for (int i = 1; i < num_steps; ++i) {
            integral += 0.5f * (cross_kernel[i] + cross_kernel[i - 1]) * dt_ns;
        }
        if (integral > 0.0f) {
            float factor = 1.0f / integral;
            for (auto& val : cross_kernel) val *= factor;
        }
    }

    float total_latency = src_kernel.peak_time_ns + total_network_latency_ns + dst_kernel.peak_time_ns;

    CrossPropagationKernel kernel;
    kernel.source = source;
    kernel.target = target;
    kernel.edge_type = edge.edge_type;
    kernel.time_axis_ns = std::move(time_axis);
    kernel.kernel_values = std::move(cross_kernel);
    kernel.total_latency_ns = total_latency;
    kernel.network_latency_ns = network_latency_ns;
    kernel.queueing_latency_ns = queueing_latency_ns;

    return kernel;
}

CrossKernelsGPU CrossKernelBuilder::upload_to_gpu(
    const std::unordered_map<std::string, CrossPropagationKernel>& kernels
) {
    CrossKernelsGPU gpu;
    gpu.num_kernels = static_cast<int>(kernels.size());

    gpu.max_time_steps = 0;
    for (const auto& [key, kernel] : kernels) {
        gpu.max_time_steps = std::max(gpu.max_time_steps, static_cast<int>(kernel.time_axis_ns.size()));
    }

    size_t num_kernels = gpu.num_kernels;
    size_t max_steps = gpu.max_time_steps;

    gpu.source_indices = static_cast<int*>(CudaMemoryManager::allocate(num_kernels * sizeof(int)));
    gpu.target_indices = static_cast<int*>(CudaMemoryManager::allocate(num_kernels * sizeof(int)));
    gpu.edge_type_indices = static_cast<int*>(CudaMemoryManager::allocate(num_kernels * sizeof(int)));
    gpu.tau_ns = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * sizeof(float)));
    gpu.total_latency_ns = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * sizeof(float)));
    gpu.network_latency_ns = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * sizeof(float)));
    gpu.queueing_latency_ns = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * sizeof(float)));
    gpu.kernel_values = static_cast<float*>(CudaMemoryManager::allocate(num_kernels * max_steps * sizeof(float)));
    gpu.time_axis_ns = static_cast<float*>(CudaMemoryManager::allocate(max_steps * sizeof(float)));

    // Prepare host buffers
    std::vector<int> h_source_indices(num_kernels);
    std::vector<int> h_target_indices(num_kernels);
    std::vector<int> h_edge_type_indices(num_kernels);
    std::vector<float> h_tau_ns(num_kernels);
    std::vector<float> h_total_latency(num_kernels);
    std::vector<float> h_network_latency(num_kernels);
    std::vector<float> h_queueing_latency(num_kernels);
    std::vector<float> h_kernel_values(num_kernels * max_steps, 0.0f);
    std::vector<float> h_time_axis(max_steps);

    size_t idx = 0;
    for (const auto& [key, kernel] : kernels) {
        if (idx == 0) {
            std::copy(kernel.time_axis_ns.begin(), kernel.time_axis_ns.end(), h_time_axis.begin());
        }
        ++idx;
    }

    idx = 0;
    for (const auto& [key, kernel] : kernels) {
        h_source_indices[idx] = static_cast<int>(std::hash<std::string>{}(kernel.source) % 10000);
        h_target_indices[idx] = static_cast<int>(std::hash<std::string>{}(kernel.target) % 10000);
        h_edge_type_indices[idx] = 0; // Simplified
        h_tau_ns[idx] = 0.0f; // Not used for cross kernels directly
        h_total_latency[idx] = kernel.total_latency_ns;
        h_network_latency[idx] = kernel.network_latency_ns;
        h_queueing_latency[idx] = kernel.queueing_latency_ns;

        size_t copy_size = std::min(kernel.kernel_values.size(), static_cast<size_t>(max_steps));
        std::copy(kernel.kernel_values.begin(), kernel.kernel_values.begin() + copy_size,
                  h_kernel_values.begin() + idx * max_steps);

        ++idx;
    }

    CudaMemoryManager::copy_host_to_device(gpu.source_indices, h_source_indices.data(), num_kernels * sizeof(int));
    CudaMemoryManager::copy_host_to_device(gpu.target_indices, h_target_indices.data(), num_kernels * sizeof(int));
    CudaMemoryManager::copy_host_to_device(gpu.edge_type_indices, h_edge_type_indices.data(), num_kernels * sizeof(int));
    CudaMemoryManager::copy_host_to_device(gpu.tau_ns, h_tau_ns.data(), num_kernels * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.total_latency_ns, h_total_latency.data(), num_kernels * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.network_latency_ns, h_network_latency.data(), num_kernels * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.queueing_latency_ns, h_queueing_latency.data(), num_kernels * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.kernel_values, h_kernel_values.data(), num_kernels * max_steps * sizeof(float));
    CudaMemoryManager::copy_host_to_device(gpu.time_axis_ns, h_time_axis.data(), max_steps * sizeof(float));

    return gpu;
}

int CrossKernelBuilder::get_component_index(const std::string& name, const std::vector<std::string>& components) const {
    auto it = std::find(components.begin(), components.end(), name);
    if (it != components.end()) {
        return static_cast<int>(std::distance(components.begin(), it));
    }
    return -1;
}

} // namespace cauveris