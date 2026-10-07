#pragma once

#include "kernel_types.h"
#include <vector>
#include <unordered_map>
#include <string>

namespace cauveris {

class LocalKernelBuilder {
public:
    explicit LocalKernelBuilder(const KernelConfig& config = KernelConfig());

    // Build all local kernels for a set of components and layers
    std::unordered_map<std::string, LocalPropagationKernel> build_kernels(
        const std::vector<std::string>& component_names,
        const std::vector<ComponentType>& component_types,
        const std::vector<std::vector<BoundaryLayer>>& component_layers
    );

    // Build a single local kernel
    LocalPropagationKernel build_kernel(
        const std::string& component_name,
        ComponentType component_type,
        BoundaryLayer layer
    );

    // Upload to GPU
    LocalKernelsGPU upload_to_gpu(
        const std::unordered_map<std::string, LocalPropagationKernel>& kernels
    );

    // Download from GPU
    std::unordered_map<std::string, LocalPropagationKernel> download_from_gpu(
        const LocalKernelsGPU& gpu_kernels
    );

    const KernelConfig& get_config() const { return config_; }
    void set_config(const KernelConfig& config) { config_ = config; }

private:
    KernelConfig config_;

    float compute_tau_ns(ComponentType type, BoundaryLayer layer) const;
    std::vector<float> generate_time_axis() const;
    std::vector<float> generate_kernel_values(float tau_ns, const std::vector<float>& time_axis) const;
    float compute_integral(const std::vector<float>& kernel, const std::vector<float>& time_axis) const;
    float compute_peak_time(const std::vector<float>& kernel, const std::vector<float>& time_axis) const;
    float compute_half_life(const std::vector<float>& kernel, const std::vector<float>& time_axis) const;
    void normalize_kernel(std::vector<float>& kernel, const std::vector<float>& time_axis) const;
};

} // namespace cauveris