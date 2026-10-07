#include "cauveris/kernel_types.h"
#include <cmath>

namespace cauveris {

__global__ void matrix_vector_multiply_kernel(
    const float* A,       // [rows * cols]
    const float* x,       // [cols]
    float* y,             // [rows]
    int rows,
    int cols
) {
    int row = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= rows) return;

    float sum = 0.0f;
    for (int col = 0; col < cols; ++col) {
        sum += A[row * cols + col] * x[col];
    }
    y[row] = sum;
}

__global__ void matrix_transpose_multiply_kernel(
    const float* A,       // [rows * cols]
    const float* x,       // [rows]
    float* y,             // [cols]
    int rows,
    int cols
) {
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    if (col >= cols) return;

    float sum = 0.0f;
    for (int row = 0; row < rows; ++row) {
        sum += A[row * cols + col] * x[row];
    }
    y[col] = sum;
}

__global__ void kernel_matrix_multiply_kernel(
    const float* K,       // [n_obs * n_comp * n_time]
    const float* x,       // [n_comp * n_time]
    float* y,             // [n_obs * n_time]
    int n_comp,
    int n_obs,
    int n_time
) {
    int obs_t = blockIdx.x * blockDim.x + threadIdx.x;
    int total_obs_time = n_obs * n_time;
    if (obs_t >= total_obs_time) return;

    int total_x = n_comp * n_time;
    int obs_idx = obs_t / n_time;
    int t_idx = obs_t % n_time;

    float sum = 0.0f;
    for (int comp = 0; comp < n_comp; ++comp) {
        for (int tau = 0; tau <= t_idx; ++tau) {
            int k_idx = (obs_idx * n_comp + comp) * n_time + tau;
            int x_idx = comp * n_time + (t_idx - tau);
            sum += K[k_idx] * x[x_idx];
        }
    }
    y[obs_t] = sum;
}

__global__ void kernel_matrix_transpose_multiply_kernel(
    const float* K,       // [n_obs * n_comp * n_time]
    const float* y,       // [n_obs * n_time]
    float* x,             // [n_comp * n_time]
    int n_comp,
    int n_obs,
    int n_time
) {
    int comp_t = blockIdx.x * blockDim.x + threadIdx.x;
    int total_comp_time = n_comp * n_time;
    if (comp_t >= total_comp_time) return;

    int comp = comp_t / n_time;
    int t_idx = comp_t % n_time;

    float sum = 0.0f;
    for (int obs = 0; obs < n_obs; ++obs) {
        for (int tau = t_idx; tau < n_time; ++tau) {
            int k_idx = (obs * n_comp + comp) * n_time + tau;
            int y_idx = obs * n_time + (tau - t_idx);
            sum += K[k_idx] * y[y_idx];
        }
    }
    x[comp_t] = sum;
}

__global__ void compute_diagonal_preconditioner_kernel(
    const float* K,       // [n_obs * n_comp * n_time]
    float* M_inv,         // [n_comp * n_time]
    int n_comp,
    int n_obs,
    int n_time,
    float reg
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total = n_comp * n_time;
    if (idx >= total) return;

    float diag = reg;
    for (int i = 0; i < n_obs * n_time; ++i) {
        diag += K[i * total + idx] * K[i * total + idx];
    }
    M_inv[idx] = 1.0f / diag;
}

__global__ void apply_preconditioner_kernel(
    const float* M_inv,   // [n]
    const float* r,       // [n]
    float* z,             // [n]
    int n
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;
    z[idx] = M_inv[idx] * r[idx];
}

__global__ void vector_add_kernel(
    float* y,             // [n]
    const float* x,       // [n]
    float alpha,
    int n
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;
    y[idx] += alpha * x[idx];
}

__global__ void vector_scale_kernel(
    float* x,             // [n]
    float alpha,
    int n
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;
    x[idx] *= alpha;
}

__global__ void vector_copy_kernel(
    float* dst,           // [n]
    const float* src,     // [n]
    int n
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;
    dst[idx] = src[idx];
}

__global__ void dot_product_kernel(
    const float* a,       // [n]
    const float* b,       // [n]
    float* result,        // [1]
    int n
) {
    extern __shared__ float sdata[];
    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float val = (i < n) ? a[i] * b[i] : 0.0f;
    sdata[tid] = val;
    __syncthreads();

    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] += sdata[tid + s];
        }
        __syncthreads();
    }

    if (tid == 0) {
        atomicAdd(result, sdata[0]);
    }
}

__global__ void axpy_kernel(
    float* y,             // [n]
    float alpha,
    const float* x,       // [n]
    int n
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n) return;
    y[idx] += alpha * x[idx];
}

__global__ void matrix_frobenius_norm_kernel(
    const float* A,       // [rows * cols]
    float* norm,          // [1]
    int rows,
    int cols
) {
    extern __shared__ float sdata[];
    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;
    int total = rows * cols;

    float val = (i < total) ? A[i] * A[i] : 0.0f;
    sdata[tid] = val;
    __syncthreads();

    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] += sdata[tid + s];
        }
        __syncthreads();
    }

    if (tid == 0) {
        atomicAdd(norm, sdata[0]);
    }
}

} // namespace cauveris