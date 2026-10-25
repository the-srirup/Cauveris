/**
 * Python bindings for the Cauveris CUDA kernels.
 *
 * The module deliberately exposes only functions that are actually
 * implemented in the CUDA translation units.  Every array argument is
 * converted to a contiguous, correctly typed buffer before it is handed to
 * the kernels, and the sizes are checked against the shapes the caller
 * claims, so a wrong shape produces an exception instead of an out of bounds
 * device read.
 */

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cuda_runtime.h>

#include <string>
#include <vector>

#include "cauveris/device.h"
#include "cauveris/kernel_types.h"
#include "cauveris/linalg.h"
#include "cauveris/propagation_kernels.h"

namespace py = pybind11;

namespace {

using FloatArray = py::array_t<float, py::array::c_style | py::array::forcecast>;
using DoubleArray = py::array_t<double, py::array::c_style | py::array::forcecast>;
using IntArray = py::array_t<int, py::array::c_style | py::array::forcecast>;

// A writable view of the same array, used when a function updates its
// output in place.
void require_writable(const py::array& array, const char* name) {
    if (!array.writeable()) {
        throw py::value_error(std::string(name) + " must be a writable array");
    }
}

py::dict solver_result_to_dict(const cauveris::SolverResult& result) {
    py::dict out;
    out["x"] = FloatArray(result.x.size(), result.x.data());
    out["iterations"] = result.iterations;
    out["residual"] = result.residual;
    out["converged"] = result.converged;
    return out;
}

}  // namespace

PYBIND11_MODULE(cauveris_kernels_py, m) {
    m.doc() = "CUDA kernels for the Cauveris holographic causal engine.";

    py::enum_<cauveris::DecayType>(m, "DecayType")
        .value("EXPONENTIAL", cauveris::DecayType::EXPONENTIAL)
        .value("GAMMA", cauveris::DecayType::GAMMA)
        .value("BI_EXPONENTIAL", cauveris::DecayType::BI_EXPONENTIAL);

    py::enum_<cauveris::NormalizationType>(m, "NormalizationType")
        .value("NONE", cauveris::NormalizationType::NONE)
        .value("L1_NORM", cauveris::NormalizationType::L1_NORM)
        .value("L2_NORM", cauveris::NormalizationType::L2_NORM)
        .value("MAX_NORM", cauveris::NormalizationType::MAX_NORM);

    py::class_<cauveris::PropagationConfig>(m, "PropagationConfig")
        .def(py::init<>())
        .def_readwrite("time_step_ns", &cauveris::PropagationConfig::time_step_ns)
        .def_readwrite("num_steps", &cauveris::PropagationConfig::num_steps)
        .def_readwrite("max_time_ns", &cauveris::PropagationConfig::max_time_ns)
        .def_readwrite("decay_type", &cauveris::PropagationConfig::decay_type)
        .def_readwrite("normalization", &cauveris::PropagationConfig::normalization)
        .def_readwrite("gamma_shape", &cauveris::PropagationConfig::gamma_shape)
        .def_readwrite("biexp_alpha", &cauveris::PropagationConfig::biexp_alpha)
        .def_readwrite("biexp_fast_ratio", &cauveris::PropagationConfig::biexp_fast_ratio);

    // ------------------------------------------------------------------
    // Device
    // ------------------------------------------------------------------

    m.def("device_count", []() -> int {
        int count = 0;
        if (cudaGetDeviceCount(&count) != cudaSuccess) {
            cudaGetLastError();
            return 0;
        }
        return count;
    });

    m.def(
        "device_info",
        [](int device_id) -> py::object {
            cauveris::DeviceInfo info;
            if (!cauveris::query_device_info(device_id, &info)) {
                // No device, or a device that does not exist.  That is an
                // answer, not a failure: the engine falls back to the CPU.
                return py::none();
            }
            py::dict out;
            out["device_id"] = info.device_id;
            out["name"] = info.name;
            out["compute_capability"] =
                std::to_string(info.compute_major) + "." + std::to_string(info.compute_minor);
            out["compute_major"] = info.compute_major;
            out["compute_minor"] = info.compute_minor;
            out["multi_processor_count"] = info.multi_processor_count;
            out["total_memory_bytes"] = info.total_memory_bytes;
            out["clock_rate_khz"] = info.clock_rate_khz;
            out["memory_clock_khz"] = info.memory_clock_khz;
            out["memory_bus_width"] = info.memory_bus_width;
            out["l2_cache_size"] = info.l2_cache_size;
            out["max_threads_per_block"] = info.max_threads_per_block;
            out["warp_size"] = info.warp_size;
            out["cuda_runtime_version"] = info.cuda_runtime_version;
            out["driver_version"] = info.driver_version;
            return out;
        },
        py::arg("device_id") = 0);

    // ------------------------------------------------------------------
    // Propagation kernels
    // ------------------------------------------------------------------

    m.def(
        "build_local_kernels",
        [](DoubleArray tau_ns, const cauveris::PropagationConfig& config, int device_id) {
            auto tau = tau_ns.request();
            const int num_pairs = static_cast<int>(tau.size);
            if (num_pairs <= 0) {
                throw py::value_error("tau_ns must not be empty");
            }
            if (config.num_steps <= 0) {
                throw py::value_error("num_steps must be positive");
            }

            const size_t value_count = static_cast<size_t>(num_pairs) * config.num_steps;

            py::array_t<float> kernels(value_count);
            py::array_t<double> integral(num_pairs);
            py::array_t<double> peak_time(num_pairs);
            py::array_t<double> half_life(num_pairs);

            cauveris::build_local_kernels(
                static_cast<const double*>(tau.ptr), num_pairs, config, device_id,
                static_cast<float*>(kernels.mutable_data()),
                static_cast<double*>(integral.mutable_data()),
                static_cast<double*>(peak_time.mutable_data()),
                static_cast<double*>(half_life.mutable_data()));

            return py::make_tuple(kernels, integral, peak_time, half_life);
        },
        py::arg("tau_ns"),
        py::arg("config"),
        py::arg("device_id") = 0);

    m.def(
        "build_cross_kernels",
        [](FloatArray src_kernel, FloatArray dst_kernel, IntArray shift_steps,
           const cauveris::PropagationConfig& config, int device_id) {
            auto src = src_kernel.request();
            auto dst = dst_kernel.request();
            auto shift = shift_steps.request();
            if (config.num_steps <= 0) {
                throw py::value_error("num_steps must be positive");
            }
            const int num_pairs = static_cast<int>(shift.size);
            if (num_pairs <= 0) {
                throw py::value_error("shift_steps must not be empty");
            }
            const size_t expected = static_cast<size_t>(num_pairs) * config.num_steps;
            if (static_cast<size_t>(src.size) != expected ||
                static_cast<size_t>(dst.size) != expected) {
                throw py::value_error(
                    "src_kernel and dst_kernel must have num_pairs * num_steps entries");
            }

            py::array_t<float> cross(expected);
            cauveris::build_cross_kernels(
                static_cast<const float*>(src.ptr), static_cast<const float*>(dst.ptr),
                static_cast<const int*>(shift.ptr), num_pairs, config, device_id,
                static_cast<float*>(cross.mutable_data()));
            return cross;
        },
        py::arg("src_kernel"),
        py::arg("dst_kernel"),
        py::arg("shift_steps"),
        py::arg("config"),
        py::arg("device_id") = 0);

    m.def(
        "assemble_kernel_matrix",
        [](FloatArray values, IntArray row_index, IntArray col_index, int num_steps, int n_time,
           int n_rows, int n_cols) {
            auto val = values.request();
            auto rows = row_index.request();
            auto cols = col_index.request();
            const int num_pairs = static_cast<int>(rows.size);
            if (num_pairs <= 0) {
                throw py::value_error("row_index must not be empty");
            }
            if (static_cast<size_t>(cols.size) != static_cast<size_t>(num_pairs)) {
                throw py::value_error("row_index and col_index must have the same length");
            }
            if (static_cast<size_t>(val.size) !=
                static_cast<size_t>(num_pairs) * static_cast<size_t>(num_steps)) {
                throw py::value_error("values must hold num_pairs * num_steps entries");
            }
            if (num_steps <= 0 || n_time <= 0 || n_rows <= 0 || n_cols <= 0) {
                throw py::value_error("the matrix dimensions must be positive");
            }

            py::array_t<float> matrix(static_cast<py::ssize_t>(n_rows) * n_cols * n_time);
            cauveris::assemble_kernel_matrix(
                static_cast<const float*>(val.ptr), static_cast<const int*>(rows.ptr),
                static_cast<const int*>(cols.ptr), num_pairs, num_steps, n_time, n_rows, n_cols,
                static_cast<float*>(matrix.mutable_data()));
            return matrix.reshape({n_rows, n_cols, n_time});
        },
        py::arg("values"),
        py::arg("row_index"),
        py::arg("col_index"),
        py::arg("num_steps"),
        py::arg("n_time"),
        py::arg("n_rows"),
        py::arg("n_cols"));

    // ------------------------------------------------------------------
    // Linear algebra
    // ------------------------------------------------------------------

    m.def(
        "matmul",
        [](FloatArray A, FloatArray B) {
            auto a = A.request();
            auto b = B.request();
            if (a.ndim != 2 || b.ndim != 2) {
                throw py::value_error("matmul expects two dimensional arrays");
            }
            const int m = static_cast<int>(a.shape[0]);
            const int k = static_cast<int>(a.shape[1]);
            const int k2 = static_cast<int>(b.shape[0]);
            const int n = static_cast<int>(b.shape[1]);
            if (k != k2) {
                throw py::value_error("inner dimensions do not agree");
            }
            py::array_t<float> C(static_cast<py::ssize_t>(m) * n);
            cauveris::matmul(static_cast<const float*>(a.ptr), static_cast<const float*>(b.ptr),
                             static_cast<float*>(C.mutable_data()), m, n, k);
            return C.reshape({m, n});
        },
        py::arg("A"),
        py::arg("B"));

    m.def(
        "batch_matmul",
        [](FloatArray A, FloatArray B) {
            auto a = A.request();
            auto b = B.request();
            if (a.ndim != 3 || b.ndim != 3) {
                throw py::value_error("batch_matmul expects three dimensional arrays");
            }
            const int batch = static_cast<int>(a.shape[0]);
            const int m = static_cast<int>(a.shape[1]);
            const int k = static_cast<int>(a.shape[2]);
            const int batch2 = static_cast<int>(b.shape[0]);
            const int k2 = static_cast<int>(b.shape[1]);
            const int n = static_cast<int>(b.shape[2]);
            if (batch != batch2 || k != k2) {
                throw py::value_error("batch and inner dimensions do not agree");
            }
            py::array_t<float> C({batch, m, n});
            cauveris::batch_matmul(static_cast<const float*>(a.ptr), static_cast<const float*>(b.ptr),
                                   static_cast<float*>(C.mutable_data()), batch, m, n, k);
            return C;
        },
        py::arg("A"),
        py::arg("B"));

    m.def(
        "dot_product",
        [](FloatArray a, FloatArray b) {
            auto x = a.request();
            auto y = b.request();
            if (x.size != y.size) {
                throw py::value_error("dot_product expects vectors of equal length");
            }
            return cauveris::dot_product(static_cast<const float*>(x.ptr),
                                         static_cast<const float*>(y.ptr),
                                         static_cast<int>(x.size));
        },
        py::arg("a"),
        py::arg("b"));

    m.def(
        "l2_norm",
        [](FloatArray x) {
            auto v = x.request();
            return cauveris::l2_norm(static_cast<const float*>(v.ptr), static_cast<int>(v.size));
        },
        py::arg("x"));

    m.def(
        "l1_norm",
        [](FloatArray x) {
            auto v = x.request();
            return cauveris::l1_norm(static_cast<const float*>(v.ptr), static_cast<int>(v.size));
        },
        py::arg("x"));

    m.def(
        "scale_vector",
        [](FloatArray y, FloatArray x, float alpha) {
            auto out = y.request();
            auto in = x.request();
            require_writable(y, "y");
            if (out.size != in.size) {
                throw py::value_error("scale_vector expects vectors of equal length");
            }
            cauveris::scale_vector(static_cast<float*>(out.ptr), static_cast<const float*>(in.ptr),
                                   alpha, static_cast<int>(out.size));
            return y;
        },
        py::arg("y"),
        py::arg("x"),
        py::arg("alpha"));

    m.def(
        "axpy",
        [](FloatArray y, FloatArray x, float alpha) {
            auto out = y.request();
            auto in = x.request();
            require_writable(y, "y");
            if (out.size != in.size) {
                throw py::value_error("axpy expects vectors of equal length");
            }
            cauveris::axpy(static_cast<float*>(out.ptr), static_cast<const float*>(in.ptr), alpha,
                           static_cast<int>(out.size));
            return y;
        },
        py::arg("y"),
        py::arg("x"),
        py::arg("alpha"));

    // ------------------------------------------------------------------
    // Solvers
    // ------------------------------------------------------------------

    m.def(
        "solve_cg_dense",
        [](FloatArray A, FloatArray b, int max_iter, float tol) {
            auto a = A.request();
            auto rhs = b.request();
            if (a.ndim != 2 || a.shape[0] != a.shape[1]) {
                throw py::value_error("A must be a square matrix");
            }
            const int n = static_cast<int>(a.shape[0]);
            if (static_cast<size_t>(rhs.size) != static_cast<size_t>(n)) {
                throw py::value_error("b must have n entries");
            }
            auto result = cauveris::solve_conjugate_gradient(
                static_cast<const float*>(a.ptr), nullptr, nullptr, nullptr,
                static_cast<const float*>(rhs.ptr), n, max_iter, tol);
            return solver_result_to_dict(result);
        },
        py::arg("A"),
        py::arg("b"),
        py::arg("max_iter") = 1000,
        py::arg("tol") = 1e-6f);

    m.def(
        "solve_cg_csr",
        [](IntArray row_ptr, IntArray col_idx, FloatArray values, FloatArray b, int max_iter,
           float tol) {
            auto rp = row_ptr.request();
            auto ci = col_idx.request();
            auto val = values.request();
            auto rhs = b.request();
            const int n = static_cast<int>(rp.size) - 1;
            if (n <= 0) {
                throw py::value_error("row_ptr must describe at least one row");
            }
            if (static_cast<size_t>(ci.size) != static_cast<size_t>(val.size)) {
                throw py::value_error("col_idx and values must have the same length");
            }
            if (static_cast<size_t>(rhs.size) != static_cast<size_t>(n)) {
                throw py::value_error("b must have n entries");
            }
            auto result = cauveris::solve_conjugate_gradient(
                nullptr, static_cast<const int*>(rp.ptr), static_cast<const int*>(ci.ptr),
                static_cast<const float*>(val.ptr), static_cast<const float*>(rhs.ptr), n, max_iter,
                tol);
            return solver_result_to_dict(result);
        },
        py::arg("row_ptr"),
        py::arg("col_idx"),
        py::arg("values"),
        py::arg("b"),
        py::arg("max_iter") = 1000,
        py::arg("tol") = 1e-6f);

    m.def(
        "solve_rls",
        [](FloatArray A, FloatArray b, FloatArray lambda, int m, int n) {
            auto a = A.request();
            auto rhs = b.request();
            auto lam = lambda.request();
            if (static_cast<size_t>(a.size) != static_cast<size_t>(m) * static_cast<size_t>(n)) {
                throw py::value_error("A must hold m * n entries");
            }
            if (static_cast<size_t>(rhs.size) != static_cast<size_t>(m)) {
                throw py::value_error("b must have m entries");
            }
            if (static_cast<size_t>(lam.size) != static_cast<size_t>(n)) {
                throw py::value_error("lambda must have n entries");
            }
            auto result = cauveris::solve_rls(
                static_cast<const float*>(a.ptr), static_cast<const float*>(rhs.ptr),
                static_cast<const float*>(lam.ptr), m, n);
            return solver_result_to_dict(result);
        },
        py::arg("A"),
        py::arg("b"),
        py::arg("lambda"),
        py::arg("m"),
        py::arg("n"));
}
