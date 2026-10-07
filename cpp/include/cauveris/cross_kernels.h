/**
 * Cross Kernel Builder - Builds cross-component causal propagation kernels.
 *
 * Constructs sparse causal dependency matrices between components based on
 * topology, communication patterns, and boundary layer correlations.
 */

#pragma once

#include "kernel_types.h"

namespace cauveris {

struct TopologyEdge {
    int source_id;
    int target_id;
    ComponentType source_type;
    ComponentType target_type;
    double latency_ns;
    double bandwidth_mbps;
    float causal_strength;  // 0.0 - 1.0
};

class CrossKernelBuilder {
public:
    CrossKernelBuilder(const KernelConfig& config = KernelConfig());
    ~CrossKernelBuilder();

    // Build cross-component kernels from topology
    void build_kernels(CrossKernelsGPU& gpu_kernels,
                       const TopologyEdge* edges,
                       int num_edges,
                       int num_components,
                       int batch_size = 1);

    // Build single cross kernel
    void build_single_kernel(CrossPropagationKernel& kernel,
                             int source_id,
                             int target_id,
                             ComponentType source_type,
                             ComponentType target_type,
                             double latency_ns,
                             float causal_strength);

    // Build from adjacency list
    void build_from_adjacency(CrossKernelsGPU& gpu_kernels,
                              const int* row_ptr,
                              const int* col_idx,
                              const float* weights,
                              int num_components,
                              int batch_size = 1);

    // Get configuration
    const KernelConfig& get_config() const { return config_; }

    // Set causal strength model
    void set_causal_model(const char* model_name);

private:
    KernelConfig config_;
    std::string causal_model_ = "latency_bandwidth";

    // Device workspace
    float* d_workspace_ = nullptr;
    size_t workspace_bytes_ = 0;
    int* d_row_ptr_ = nullptr;
    int* d_col_idx_ = nullptr;
    float* d_weights_ = nullptr;

    void allocate_workspace(int num_edges, int num_components);
    void free_workspace();

    // Causal strength computation
    __device__ __host__ float compute_causal_strength(const TopologyEdge& edge) const;
};

} // namespace cauveris