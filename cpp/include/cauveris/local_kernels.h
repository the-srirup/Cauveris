/**
 * Local Kernel Builder - Builds per-component boundary propagation kernels on GPU.
 *
 * Provides high-performance GPU kernels for constructing local propagation kernels
 * with support for multiple decay functions and causal cone truncation.
 */

#pragma once

#include "kernel_types.h"

namespace cauveris {

class LocalKernelBuilder {
public:
    LocalKernelBuilder(const KernelConfig& config = KernelConfig());
    ~LocalKernelBuilder();

    // Build local kernels for a batch of components
    void build_kernels(LocalKernelsGPU& gpu_kernels,
                       const int* component_ids,
                       const ComponentType* component_types,
                       int num_components,
                       int batch_size = 1);

    // Build single kernel for a component-layer pair
    void build_single_kernel(LocalPropagationKernel& kernel,
                             int component_id,
                             ComponentType comp_type,
                             BoundaryLayer layer);

    // Build all layers for a component
    void build_component_kernels(std::array<LocalPropagationKernel, KERNELS_PER_COMPONENT>& kernels,
                                 int component_id,
                                 ComponentType comp_type);

    // Get configuration
    const KernelConfig& get_config() const { return config_; }

    // Set custom decay parameters for a component type
    void set_component_decay(ComponentType type, DecayType decay, const double params[4]);

    // Set custom layer weight
    void set_layer_weight(BoundaryLayer layer, double weight);

private:
    KernelConfig config_;

    // Device pointers for kernel launches
    int* d_component_ids_ = nullptr;
    ComponentType* d_component_types_ = nullptr;

    // Workspace buffers
    float* d_workspace_ = nullptr;
    size_t workspace_bytes_ = 0;

    void allocate_workspace(int max_components, int time_steps);
    void free_workspace();
};

} // namespace cauveris