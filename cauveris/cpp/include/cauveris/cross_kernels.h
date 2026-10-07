#pragma once

#include "kernel_types.h"
#include "local_kernels.h"
#include <vector>
#include <unordered_map>
#include <string>

namespace cauveris {

struct CausalEdge {
    std::string source;
    std::string target;
    float latency_ms;
    int queue_depth;
    std::string edge_type;
};

class CrossKernelBuilder {
public:
    explicit CrossKernelBuilder(const KernelConfig& config = KernelConfig());

    // Build all cross kernels for a set of components and edges
    std::unordered_map<std::string, CrossPropagationKernel> build_kernels(
        const std::vector<std::string>& component_names,
        const std::vector<ComponentType>& component_types,
        const std::vector<std::vector<BoundaryLayer>>& component_layers,
        const std::vector<CausalEdge>& edges,
        const LocalKernelBuilder& local_builder
    );

    // Build a single cross kernel
    CrossPropagationKernel build_kernel(
        const std::string& source,
        const std::string& target,
        const CausalEdge& edge,
        BoundaryLayer src_layer,
        BoundaryLayer dst_layer,
        const LocalKernelBuilder& local_builder
    );

    // Upload to GPU
    CrossKernelsGPU upload_to_gpu(
        const std::unordered_map<std::string, CrossPropagationKernel>& kernels
    );

    const KernelConfig& get_config() const { return config_; }
    void set_config(const KernelConfig& config) { config_ = config; }

private:
    KernelConfig config_;

    int get_component_index(const std::string& name, const std::vector<std::string>& components) const;
};

} // namespace cauveris