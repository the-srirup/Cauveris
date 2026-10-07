#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <pybind11/functional.h>

#include "cauveris/kernel_types.h"
#include "cauveris/local_kernels.h"
#include "cauveris/cross_kernels.h"

namespace py = pybind11;
using namespace cauveris;

PYBIND11_MODULE(cauveris_kernels_py, m) {
    m.doc() = "Cauveris Holographic Kernel GPU Acceleration Library";

    // Enums
    py::enum_<BoundaryLayer>(m, "BoundaryLayer")
        .value("APPLICATION_LOG", BoundaryLayer::APPLICATION_LOG)
        .value("METRICS_EXPORT", BoundaryLayer::METRICS_EXPORT)
        .value("DISTRIBUTED_TRACE", BoundaryLayer::DISTRIBUTED_TRACE)
        .value("NETWORK_FLOW", BoundaryLayer::NETWORK_FLOW)
        .value("INFRASTRUCTURE_LOG", BoundaryLayer::INFRASTRUCTURE_LOG)
        .value("CONFIG_STATE", BoundaryLayer::CONFIG_STATE)
        .value("DEPLOYMENT_EVENT", BoundaryLayer::DEPLOYMENT_EVENT)
        .value("COUNT", BoundaryLayer::COUNT);

    py::enum_<ComponentType>(m, "ComponentType")
        .value("SERVICE", ComponentType::SERVICE)
        .value("DATABASE", ComponentType::DATABASE)
        .value("CACHE", ComponentType::CACHE)
        .value("GATEWAY", ComponentType::GATEWAY)
        .value("MESSAGE_QUEUE", ComponentType::MESSAGE_QUEUE)
        .value("MONITORING", ComponentType::MONITORING)
        .value("COUNT", ComponentType::COUNT);

    py::enum_<DecayType>(m, "DecayType")
        .value("EXPONENTIAL", DecayType::EXPONENTIAL)
        .value("GAMMA", DecayType::GAMMA)
        .value("BI_EXPONENTIAL", DecayType::BI_EXPONENTIAL);

    py::enum_<NormalizationType>(m, "NormalizationType")
        .value("L1", NormalizationType::L1)
        .value("L2", NormalizationType::L2)
        .value("MAX", NormalizationType::MAX);

    // KernelConfig
    py::class_<KernelConfig>(m, "KernelConfig")
        .def(py::init<>())
        .def_readwrite("time_step_ns", &KernelConfig::time_step_ns)
        .def_readwrite("max_kernel_time_ns", &KernelConfig::max_kernel_time_ns)
        .def_readwrite("self_latency_factor", &KernelConfig::self_latency_factor)
        .def_readwrite("queue_service_time_ms", &KernelConfig::queue_service_time_ms)
        .def_readwrite("decay_type", &KernelConfig::decay_type)
        .def_readwrite("normalization", &KernelConfig::normalization);

    // LocalPropagationKernel
    py::class_<LocalPropagationKernel>(m, "LocalPropagationKernel")
        .def(py::init<>())
        .def_readwrite("component_name", &LocalPropagationKernel::component_name)
        .def_readwrite("boundary_layer", &LocalPropagationKernel::boundary_layer)
        .def_readwrite("time_axis_ns", &LocalPropagationKernel::time_axis_ns)
        .def_readwrite("kernel_values", &LocalPropagationKernel::kernel_values)
        .def_readwrite("integral", &LocalPropagationKernel::integral)
        .def_readwrite("peak_time_ns", &LocalPropagationKernel::peak_time_ns)
        .def_readwrite("half_life_ns", &LocalPropagationKernel::half_life_ns)
        .def("evaluate_at", &LocalPropagationKernel::evaluate_at);

    // CrossPropagationKernel
    py::class_<CrossPropagationKernel>(m, "CrossPropagationKernel")
        .def(py::init<>())
        .def_readwrite("source", &CrossPropagationKernel::source)
        .def_readwrite("target", &CrossPropagationKernel::target)
        .def_readwrite("edge_type", &CrossPropagationKernel::edge_type)
        .def_readwrite("time_axis_ns", &CrossPropagationKernel::time_axis_ns)
        .def_readwrite("kernel_values", &CrossPropagationKernel::kernel_values)
        .def_readwrite("total_latency_ns", &CrossPropagationKernel::total_latency_ns)
        .def_readwrite("network_latency_ns", &CrossPropagationKernel::network_latency_ns)
        .def_readwrite("queueing_latency_ns", &CrossPropagationKernel::queueing_latency_ns);

    // CausalEdge
    py::class_<CausalEdge>(m, "CausalEdge")
        .def(py::init<>())
        .def_readwrite("source", &CausalEdge::source)
        .def_readwrite("target", &CausalEdge::target)
        .def_readwrite("latency_ms", &CausalEdge::latency_ms)
        .def_readwrite("queue_depth", &CausalEdge::queue_depth)
        .def_readwrite("edge_type", &CausalEdge::edge_type);

    // LocalKernelBuilder
    py::class_<LocalKernelBuilder>(m, "LocalKernelBuilder")
        .def(py::init<const KernelConfig&>(), py::arg("config") = KernelConfig())
        .def("build_kernels", &LocalKernelBuilder::build_kernels,
             py::arg("component_names"), py::arg("component_types"), py::arg("component_layers"))
        .def("build_kernel", &LocalKernelBuilder::build_kernel,
             py::arg("component_name"), py::arg("component_type"), py::arg("layer"))
        .def("get_config", &LocalKernelBuilder::get_config)
        .def("set_config", &LocalKernelBuilder::set_config);

    // CrossKernelBuilder
    py::class_<CrossKernelBuilder>(m, "CrossKernelBuilder")
        .def(py::init<const KernelConfig&>(), py::arg("config") = KernelConfig())
        .def("build_kernels", &CrossKernelBuilder::build_kernels,
             py::arg("component_names"), py::arg("component_types"),
             py::arg("component_layers"), py::arg("edges"), py::arg("local_builder"))
        .def("build_kernel", &CrossKernelBuilder::build_kernel,
             py::arg("source"), py::arg("target"), py::arg("edge"),
             py::arg("src_layer"), py::arg("dst_layer"), py::arg("local_builder"))
        .def("get_config", &CrossKernelBuilder::get_config)
        .def("set_config", &CrossKernelBuilder::set_config);

    // GPU kernels (for direct GPU access)
    py::class_<LocalKernelsGPU>(m, "LocalKernelsGPU")
        .def(py::init<>())
        .def_readwrite("num_kernels", &LocalKernelsGPU::num_kernels)
        .def_readwrite("max_time_steps", &LocalKernelsGPU::max_time_steps);

    py::class_<CrossKernelsGPU>(m, "CrossKernelsGPU")
        .def(py::init<>())
        .def_readwrite("num_kernels", &CrossKernelsGPU::num_kernels)
        .def_readwrite("max_time_steps", &CrossKernelsGPU::max_time_steps);

    // High-level convenience functions
    m.def("build_local_kernels", [](const std::vector<std::string>& component_names,
                                     const std::vector<int>& component_types,
                                     const std::vector<std::vector<int>>& component_layers,
                                     const KernelConfig& config = KernelConfig()) {
        std::vector<ComponentType> types;
        for (int t : component_types) types.push_back(static_cast<ComponentType>(t));

        std::vector<std::vector<BoundaryLayer>> layers;
        for (const auto& l : component_layers) {
            std::vector<BoundaryLayer> layer_vec;
            for (int v : l) layer_vec.push_back(static_cast<BoundaryLayer>(v));
            layers.push_back(layer_vec);
        }

        LocalKernelBuilder builder(config);
        return builder.build_kernels(component_names, types, layers);
    }, py::arg("component_names"), py::arg("component_types"), py::arg("component_layers"),
       py::arg("config") = KernelConfig());

    m.def("build_cross_kernels", [](const std::vector<std::string>& component_names,
                                     const std::vector<int>& component_types,
                                     const std::vector<std::vector<int>>& component_layers,
                                     const std::vector<CausalEdge>& edges,
                                     const LocalKernelBuilder& local_builder) {
        std::vector<ComponentType> types;
        for (int t : component_types) types.push_back(static_cast<ComponentType>(t));

        std::vector<std::vector<BoundaryLayer>> layers;
        for (const auto& l : component_layers) {
            std::vector<BoundaryLayer> layer_vec;
            for (int v : l) layer_vec.push_back(static_cast<BoundaryLayer>(v));
            layers.push_back(layer_vec);
        }

        CrossKernelBuilder builder(local_builder.get_config());
        return builder.build_kernels(component_names, types, layers, edges, local_builder);
    }, py::arg("component_names"), py::arg("component_types"), py::arg("component_layers"),
       py::arg("edges"), py::arg("local_builder"));

    // Solver config and result
    py::class_<SolverConfig>(m, "SolverConfig")
        .def(py::init<>())
        .def_readwrite("max_iterations", &SolverConfig::max_iterations)
        .def_readwrite("tolerance", &SolverConfig::tolerance)
        .def_readwrite("regularization", &SolverConfig::regularization)
        .def_readwrite("use_gpu", &SolverConfig::use_gpu)
        .def_readwrite("gpu_device_id", &SolverConfig::gpu_device_id);

    py::class_<SolverResult>(m, "SolverResult")
        .def(py::init<>())
        .def_readwrite("reconstructed_state", &SolverResult::reconstructed_state)
        .def_readwrite("residuals", &SolverResult::residuals)
        .def_readwrite("iterations", &SolverResult::iterations)
        .def_readwrite("final_residual", &SolverResult::final_residual)
        .def_readwrite("converged", &SolverResult::converged)
        .def_readwrite("solve_time_ms", &SolverResult::solve_time_ms);

    // GPU solver function
    m.def("solve_reconstruction", [](const std::vector<float>& kernel_matrix,
                                      const std::vector<float>& measurements,
                                      int n_comp, int n_obs, int n_time,
                                      const SolverConfig& config = SolverConfig()) {
        // Placeholder for GPU solver
        SolverResult result;
        result.reconstructed_state.resize(n_comp * n_time, 0.0f);
        result.residuals.resize(n_obs * n_time, 0.0f);
        result.iterations = 0;
        result.final_residual = 0.0f;
        result.converged = false;
        result.solve_time_ms = 0.0f;
        return result;
    }, py::arg("kernel_matrix"), py::arg("measurements"), py::arg("n_comp"),
       py::arg("n_obs"), py::arg("n_time"), py::arg("config") = SolverConfig());

    // Convolution
    m.def("convolve", [](const std::vector<float>& signal,
                          const std::vector<float>& kernel,
                          float dt_ns) {
        int signal_len = signal.size();
        int kernel_len = kernel.size();
        std::vector<float> output(signal_len, 0.0f);

        for (int i = 0; i < signal_len; ++i) {
            float sum = 0.0f;
            int k_max = std::min(kernel_len, i + 1);
            for (int k = 0; k < k_max; ++k) {
                sum += signal[i - k] * kernel[k];
            }
            output[i] = sum * (dt_ns / 1'000'000'000.0f);
        }
        return output;
    }, py::arg("signal"), py::arg("kernel"), py::arg("dt_ns"));

    // Batch convolution
    m.def("batch_convolve", [](const std::vector<std::vector<float>>& signals,
                                const std::vector<std::vector<float>>& kernels,
                                float dt_ns) {
        std::vector<std::vector<float>> outputs;
        for (size_t i = 0; i < signals.size(); ++i) {
            outputs.push_back(convolve(signals[i], kernels[i], dt_ns));
        }
        return outputs;
    }, py::arg("signals"), py::arg("kernels"), py::arg("dt_ns"));

    // Version
    m.attr("__version__") = "1.0.0";
}