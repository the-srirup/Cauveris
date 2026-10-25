/**
 * CUDA evaluation of the holographic propagation kernels.
 *
 * The reference implementation of this model lives in Python
 * (cauveris/holographic/heu_kernel.py).  These kernels reproduce it
 * exactly: the same density functions, the same trapezoid rule for the
 * integral, the same peak and half life definitions.  The characteristic
 * time of every (component, layer) pair is passed in, so the policy of the
 * model is not duplicated here.
 */

#include "cauveris/propagation_kernels.h"

#include <cuda_runtime.h>

#include <cmath>

#include "cauveris/cuda_utils.h"

namespace cauveris {
namespace {

// The density of the influence at time t [ns] for a characteristic time tau.
//
//   EXPONENTIAL     exp(-t/tau) / tau
//   GAMMA           Gamma PDF with shape k and scale tau/k
//   BI_EXPONENTIAL  fast (0.1 tau) plus slow (tau) exponential component
__device__ __host__ inline double decay_density(double t, double tau, const PropagationConfig& cfg) {
    switch (cfg.decay_type) {
        case DecayType::GAMMA: {
            const double k = cfg.gamma_shape;
            const double scale = tau / k;
            if (t <= 0.0) {
                return 0.0;
            }
            // Computed in log space: t^(k-1) can overflow for long windows,
            // and the ratio is what carries the meaning.
            const double log_num = (k - 1.0) * log(t) - t / scale;
            const double log_den = k * log(scale) + lgamma(k);
            return exp(log_num - log_den);
        }
        case DecayType::BI_EXPONENTIAL: {
            const double tau_fast = tau * cfg.biexp_fast_ratio;
            return cfg.biexp_alpha * exp(-t / tau_fast) / tau_fast +
                   (1.0 - cfg.biexp_alpha) * exp(-t / tau) / tau;
        }
        case DecayType::EXPONENTIAL:
        default:
            return exp(-t / tau) / tau;
    }
}

// One thread per (component, layer) pair.  The pair owns its own time
// series, so it walks the window once, keeps the running statistics, and
// writes the scaled kernel.
__global__ void eval_local_kernels_kernel(const double* __restrict__ tau_ns,
                                          int num_pairs,
                                          PropagationConfig cfg,
                                          float* __restrict__ kernel_out,
                                          double* __restrict__ integral_out,
                                          double* __restrict__ peak_time_out,
                                          double* __restrict__ half_life_out) {
    const int pair = blockIdx.x * blockDim.x + threadIdx.x;
    if (pair >= num_pairs) {
        return;
    }

    const int steps = cfg.num_steps;
    const double dt = cfg.time_step_ns;
    const double tau = tau_ns[pair];
    float* out = kernel_out + static_cast<size_t>(pair) * steps;

    // First pass: the raw density, its integral, the integral of its
    // square, and its peak.
    double prev = 0.0;
    double integral = 0.0;
    double integral_sq = 0.0;
    double peak_value = 0.0;
    int peak_index = 0;

    for (int t = 0; t < steps; ++t) {
        const double value = decay_density(static_cast<double>(t) * dt, tau, cfg);
        out[t] = static_cast<float>(value);
        if (t > 0) {
            integral += 0.5 * (prev + value) * dt;
            integral_sq += 0.5 * (prev * prev + value * value) * dt;
        }
        prev = value;
        if (value > peak_value) {
            peak_value = value;
            peak_index = t;
        }
    }

    double scale = 1.0;
    switch (cfg.normalization) {
        case NormalizationType::L1_NORM:
            scale = (integral > 0.0) ? 1.0 / integral : 1.0;
            break;
        case NormalizationType::L2_NORM:
            scale = (integral_sq > 0.0) ? 1.0 / sqrt(integral_sq) : 1.0;
            break;
        case NormalizationType::MAX_NORM:
            scale = (peak_value > 0.0) ? 1.0 / peak_value : 1.0;
            break;
        case NormalizationType::NONE:
        default:
            scale = 1.0;
            break;
    }

    // Second pass: scale the kernel, integrate the scaled kernel and find
    // the half life.  The comparisons are done on the unscaled density:
    // scaling by a positive factor does not change where the kernel has
    // fallen to half of its peak.
    const double half_threshold = peak_value * 0.5;
    double scaled_integral = 0.0;
    double prev_scaled = 0.0;
    double half_life = cfg.max_time_ns;

    for (int t = 0; t < steps; ++t) {
        const double value = decay_density(static_cast<double>(t) * dt, tau, cfg);
        const double scaled = value * scale;
        out[t] = static_cast<float>(scaled);
        if (t > 0) {
            scaled_integral += 0.5 * (prev_scaled + scaled) * dt;
        }
        prev_scaled = scaled;
        if (t >= peak_index && half_life == cfg.max_time_ns && value <= half_threshold) {
            half_life = static_cast<double>(t) * dt;
        }
    }

    integral_out[pair] = scaled_integral;
    peak_time_out[pair] = static_cast<double>(peak_index) * dt;
    half_life_out[pair] = half_life;
}

// One block per (source, target, layer pair).  The threads of the block
// split the time axis, so a pair is convolved in parallel over its window.
__global__ void cross_convolve_kernel(const float* __restrict__ src,
                                      const float* __restrict__ dst,
                                      const int* __restrict__ shift_steps,
                                      int num_steps,
                                      float* __restrict__ out) {
    const int pair = blockIdx.x;
    const int shift = shift_steps[pair];

    const float* s = src + static_cast<size_t>(pair) * num_steps;
    const float* d = dst + static_cast<size_t>(pair) * num_steps;
    float* o = out + static_cast<size_t>(pair) * num_steps;

    for (int t = threadIdx.x; t < num_steps; t += blockDim.x) {
        float acc = 0.0f;
        if (t >= shift) {
            // cross(t) = sum_j src(j) * dst(t - shift - j)
            const int last = min(t - shift, num_steps - 1);
            for (int j = 0; j <= last; ++j) {
                acc += s[j] * d[t - shift - j];
            }
        }
        o[t] = acc;
    }
}

// One thread per pair: integrate the convolution with the trapezoid rule
// and scale it, so that the transported influence is conserved.
__global__ void cross_normalize_kernel(float* __restrict__ values,
                                        int num_pairs,
                                        int num_steps,
                                        double dt,
                                        int normalize) {
    const int pair = blockIdx.x * blockDim.x + threadIdx.x;
    if (pair >= num_pairs) {
        return;
    }

    float* v = values + static_cast<size_t>(pair) * num_steps;

    if (normalize) {
        double integral = 0.0;
        double prev = v[0];
        for (int t = 1; t < num_steps; ++t) {
            const double cur = v[t];
            integral += 0.5 * (prev + cur) * dt;
            prev = cur;
        }
        const float scale = (integral > 0.0) ? static_cast<float>(1.0 / integral) : 1.0f;
        for (int t = 0; t < num_steps; ++t) {
            v[t] *= scale;
        }
    }
}

// One thread per (pair, sample): write the kernel of the pair into the slot
// of the matrix that the pair belongs to.
__global__ void assemble_kernel_matrix_kernel(const float* __restrict__ values,
                                              const int* __restrict__ row_index,
                                              const int* __restrict__ col_index,
                                              int num_pairs,
                                              int num_steps,
                                              int n_time,
                                              int n_cols,
                                              float* __restrict__ matrix) {
    const int pair = blockIdx.y;
    if (pair >= num_pairs) {
        return;
    }
    const int count = min(num_steps, n_time);
    const int t = blockIdx.x * blockDim.x + threadIdx.x;
    if (t >= count) {
        return;
    }
    const size_t dst =
        (static_cast<size_t>(row_index[pair]) * n_cols + col_index[pair]) * n_time + t;
    matrix[dst] = values[static_cast<size_t>(pair) * num_steps + t];
}

}  // namespace

void build_local_kernels(const double* tau_ns,
                         int num_pairs,
                         const PropagationConfig& config,
                         int device_id,
                         float* kernel_values,
                         double* integral,
                         double* peak_time_ns,
                         double* half_life_ns) {
    if (num_pairs <= 0 || config.num_steps <= 0) {
        return;
    }

    CAUVERIS_CUDA_CHECK(cudaSetDevice(device_id));

    const size_t value_count = static_cast<size_t>(num_pairs) * config.num_steps;

    double* d_tau = nullptr;
    float* d_values = nullptr;
    double* d_integral = nullptr;
    double* d_peak = nullptr;
    double* d_half = nullptr;

    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_tau, num_pairs * sizeof(double)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_values, value_count * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_integral, num_pairs * sizeof(double)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_peak, num_pairs * sizeof(double)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_half, num_pairs * sizeof(double)));

    CAUVERIS_CUDA_CHECK(cudaMemcpy(d_tau, tau_ns, num_pairs * sizeof(double),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemset(d_values, 0, value_count * sizeof(float)));

    const int threads = 128;
    const int blocks = (num_pairs + threads - 1) / threads;
    eval_local_kernels_kernel<<<blocks, threads>>>(d_tau, num_pairs, config, d_values, d_integral,
                                                   d_peak, d_half);
    CAUVERIS_CUDA_CHECK_KERNEL();

    CAUVERIS_CUDA_CHECK(cudaMemcpy(kernel_values, d_values, value_count * sizeof(float),
                                   cudaMemcpyDeviceToHost));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(integral, d_integral, num_pairs * sizeof(double),
                                   cudaMemcpyDeviceToHost));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(peak_time_ns, d_peak, num_pairs * sizeof(double),
                                   cudaMemcpyDeviceToHost));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(half_life_ns, d_half, num_pairs * sizeof(double),
                                   cudaMemcpyDeviceToHost));

    CAUVERIS_CUDA_CHECK(cudaFree(d_tau));
    CAUVERIS_CUDA_CHECK(cudaFree(d_values));
    CAUVERIS_CUDA_CHECK(cudaFree(d_integral));
    CAUVERIS_CUDA_CHECK(cudaFree(d_peak));
    CAUVERIS_CUDA_CHECK(cudaFree(d_half));
}

void build_cross_kernels(const float* src_kernel,
                         const float* dst_kernel,
                         const int* shift_steps,
                         int num_pairs,
                         const PropagationConfig& config,
                         int device_id,
                         float* cross_values) {
    if (num_pairs <= 0 || config.num_steps <= 0) {
        return;
    }

    CAUVERIS_CUDA_CHECK(cudaSetDevice(device_id));

    const size_t value_count = static_cast<size_t>(num_pairs) * config.num_steps;

    float* d_src = nullptr;
    float* d_dst = nullptr;
    int* d_shift = nullptr;
    float* d_out = nullptr;

    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_src, value_count * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_dst, value_count * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_shift, num_pairs * sizeof(int)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_out, value_count * sizeof(float)));

    CAUVERIS_CUDA_CHECK(cudaMemcpy(d_src, src_kernel, value_count * sizeof(float),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(d_dst, dst_kernel, value_count * sizeof(float),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(d_shift, shift_steps, num_pairs * sizeof(int),
                                   cudaMemcpyHostToDevice));

    const int threads = 256;
    cross_convolve_kernel<<<num_pairs, threads>>>(d_src, d_dst, d_shift, config.num_steps, d_out);
    CAUVERIS_CUDA_CHECK_KERNEL();

    // The reference implementation conserves the transported influence for
    // the L1 normalization only; the other modes are left alone there, and
    // this path follows it so that both agree.
    const int normalize = (config.normalization == NormalizationType::L1_NORM) ? 1 : 0;
    const int norm_threads = 128;
    const int norm_blocks = (num_pairs + norm_threads - 1) / norm_threads;
    cross_normalize_kernel<<<norm_blocks, norm_threads>>>(d_out, num_pairs, config.num_steps,
                                                           config.time_step_ns, normalize);
    CAUVERIS_CUDA_CHECK_KERNEL();

    CAUVERIS_CUDA_CHECK(cudaMemcpy(cross_values, d_out, value_count * sizeof(float),
                                   cudaMemcpyDeviceToHost));

    CAUVERIS_CUDA_CHECK(cudaFree(d_src));
    CAUVERIS_CUDA_CHECK(cudaFree(d_dst));
    CAUVERIS_CUDA_CHECK(cudaFree(d_shift));
    CAUVERIS_CUDA_CHECK(cudaFree(d_out));
}

void assemble_kernel_matrix(const float* values,
                             const int* row_index,
                             const int* col_index,
                             int num_pairs,
                             int num_steps,
                             int n_time,
                             int n_rows,
                             int n_cols,
                             float* matrix) {
    if (num_pairs <= 0 || num_steps <= 0 || n_time <= 0 || n_rows <= 0 || n_cols <= 0) {
        return;
    }

    CAUVERIS_CUDA_CHECK(cudaSetDevice(0));

    const size_t matrix_count = static_cast<size_t>(n_rows) * n_cols * n_time;

    float* d_values = nullptr;
    int* d_row = nullptr;
    int* d_col = nullptr;
    float* d_matrix = nullptr;

    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_values, static_cast<size_t>(num_pairs) * num_steps * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_row, num_pairs * sizeof(int)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_col, num_pairs * sizeof(int)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_matrix, matrix_count * sizeof(float)));

    CAUVERIS_CUDA_CHECK(cudaMemcpy(d_values, values,
                                   static_cast<size_t>(num_pairs) * num_steps * sizeof(float),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(d_row, row_index, num_pairs * sizeof(int),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(d_col, col_index, num_pairs * sizeof(int),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemset(d_matrix, 0, matrix_count * sizeof(float)));

    const int count = min(num_steps, n_time);
    const int threads = 256;
    dim3 block(threads, 1);
    dim3 grid((count + threads - 1) / threads, num_pairs, 1);
    assemble_kernel_matrix_kernel<<<grid, block>>>(d_values, d_row, d_col, num_pairs, num_steps,
                                                    n_time, n_cols, d_matrix);
    CAUVERIS_CUDA_CHECK_KERNEL();

    CAUVERIS_CUDA_CHECK(cudaMemcpy(matrix, d_matrix, matrix_count * sizeof(float),
                                   cudaMemcpyDeviceToHost));

    CAUVERIS_CUDA_CHECK(cudaFree(d_values));
    CAUVERIS_CUDA_CHECK(cudaFree(d_row));
    CAUVERIS_CUDA_CHECK(cudaFree(d_col));
    CAUVERIS_CUDA_CHECK(cudaFree(d_matrix));
}

}  // namespace cauveris
