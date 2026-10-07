/**
 * CUDA Kernels for Iterative Solvers (CG, ADMM, RLS).
 *
 * High-performance GPU implementations of linear solvers for
 * holographic reconstruction inverse problems.
 */

#include "cauveris/kernel_types.h"
#include <cuda_runtime.h>
#include <cublas_v2.h>
#include <cusparse_v2.h>
#include <cmath>
#include <cstdio>

namespace cauveris {

// ============================================================================
// Dot Product and Norm Kernels
// ============================================================================

__global__ void dot_product_kernel(const float* __restrict__ a,
                                    const float* __restrict__ b,
                                    float* result,
                                    int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float sum = 0.0f;
    while (i < n) {
        sum += a[i] * b[i];
        i += blockDim.x * gridDim.x;
    }

    sdata[tid] = sum;
    __syncthreads();

    // Reduction in shared memory
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

__global__ void norm2_kernel(const float* __restrict__ a,
                             float* result,
                             int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float sum = 0.0f;
    while (i < n) {
        float val = a[i];
        sum += val * val;
        i += blockDim.x * gridDim.x;
    }

    sdata[tid] = sum;
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

// ============================================================================
// Vector Operations (AXPY, SCAL, COPY)
// ============================================================================

__global__ void axpy_kernel(float* __restrict__ y,
                            const float* __restrict__ x,
                            float alpha,
                            int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        y[i] += alpha * x[i];
    }
}

__global__ void scal_kernel(float* __restrict__ x,
                            float alpha,
                            int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        x[i] *= alpha;
    }
}

__global__ void copy_kernel(float* __restrict__ dst,
                            const float* __restrict__ src,
                            int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        dst[i] = src[i];
    }
}

__global__ void add_kernel(float* __restrict__ dst,
                           const float* __restrict__ a,
                           const float* __restrict__ b,
                           int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        dst[i] = a[i] + b[i];
    }
}

__global__ void sub_kernel(float* __restrict__ dst,
                           const float* __restrict__ a,
                           const float* __restrict__ b,
                           int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        dst[i] = a[i] - b[i];
    }
}

// ============================================================================
// Sparse Matrix-Vector Multiplication (SpMV) - CSR Format
// ============================================================================

__global__ void spmv_csr_kernel(const int* __restrict__ row_ptr,
                                const int* __restrict__ col_idx,
                                const float* __restrict__ values,
                                const float* __restrict__ x,
                                float* __restrict__ y,
                                int num_rows) {
    int row = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= num_rows) return;

    float sum = 0.0f;
    int start = row_ptr[row];
    int end = row_ptr[row + 1];

    for (int idx = start; idx < end; ++idx) {
        sum += values[idx] * x[col_idx[idx]];
    }
    y[row] = sum;
}

__global__ void spmv_csr_transpose_kernel(const int* __restrict__ row_ptr,
                                          const int* __restrict__ col_idx,
                                          const float* __restrict__ values,
                                          const float* __restrict__ x,
                                          float* __restrict__ y,
                                          int num_rows) {
    int row = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= num_rows) return;

    float sum = 0.0f;
    // For transpose, we need to find all entries where col_idx == row
    // This is inefficient for CSR; better to use CSC or symmetrical matrix
    // Placeholder for transpose SpMV
    for (int i = 0; i < num_rows; ++i) {
        int start = row_ptr[i];
        int end = row_ptr[i + 1];
        for (int idx = start; idx < end; ++idx) {
            if (col_idx[idx] == row) {
                sum += values[idx] * x[i];
            }
        }
    }
    y[row] = sum;
}

// ============================================================================
// Dense Matrix-Vector Multiplication
// ============================================================================

__global__ void gemv_kernel(const float* __restrict__ A,
                            const float* __restrict__ x,
                            float* __restrict__ y,
                            int m, int n) {
    int row = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= m) return;

    float sum = 0.0f;
    for (int col = 0; col < n; ++col) {
        sum += A[row * n + col] * x[col];
    }
    y[row] = sum;
}

__global__ void gemv_transpose_kernel(const float* __restrict__ A,
                                      const float* __restrict__ x,
                                      float* __restrict__ y,
                                      int m, int n) {
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    if (col >= n) return;

    float sum = 0.0f;
    for (int row = 0; row < m; ++row) {
        sum += A[row * n + col] * x[row];
    }
    y[col] = sum;
}

// ============================================================================
// Conjugate Gradient Solver
// ============================================================================

__global__ void cg_init_kernel(CGState state,
                               const float* __restrict__ b,
                               int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;

    state.x[i] = 0.0f;        // Initial guess x = 0
    state.r[i] = b[i];        // r = b - A*x = b
    state.p[i] = b[i];        // p = r
}

__global__ void cg_compute_Ap_kernel(const CGState state,
                                     const float* __restrict__ A,
                                     int n) {
    // Dense A * p
    int row = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= n) return;

    float sum = 0.0f;
    for (int col = 0; col < n; ++col) {
        sum += A[row * n + col] * state.p[col];
    }
    state.Ap[row] = sum;
}

__global__ void cg_compute_Ap_sparse_kernel(const CGState state,
                                            const int* __restrict__ row_ptr,
                                            const int* __restrict__ col_idx,
                                            const float* __restrict__ values,
                                            int n) {
    int row = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= n) return;

    float sum = 0.0f;
    int start = row_ptr[row];
    int end = row_ptr[row + 1];

    for (int idx = start; idx < end; ++idx) {
        sum += values[idx] * state.p[col_idx[idx]];
    }
    state.Ap[row] = sum;
}

__global__ void cg_update_alpha_kernel(CGState state,
                                       int n) {
    // Compute alpha = (r^T r) / (p^T Ap)
    // This is done on host after dot products
}

__global__ void cg_update_x_r_kernel(CGState state,
                                     float alpha,
                                     int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;

    state.x[i] += alpha * state.p[i];
    state.r[i] -= alpha * state.Ap[i];
}

__global__ void cg_update_beta_p_kernel(CGState state,
                                        float beta,
                                        int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;

    state.p[i] = state.r[i] + beta * state.p[i];
}

__global__ void cg_check_convergence_kernel(const CGState state,
                                            float* residual_norm,
                                            float tolerance,
                                            int n) {
    // Compute ||r||^2
    extern __shared__ float sdata[];
    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float sum = 0.0f;
    while (i < n) {
        float val = state.r[i];
        sum += val * val;
        i += blockDim.x * gridDim.x;
    }

    sdata[tid] = sum;
    __syncthreads();

    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] += sdata[tid + s];
        }
        __syncthreads();
    }

    if (tid == 0) {
        *residual_norm = sqrtf(sdata[0]);
    }
}

// ============================================================================
// Preconditioned Conjugate Gradient (Jacobi preconditioner)
// ============================================================================

__global__ void pcg_apply_jacobi(const float* __restrict__ diag,
                                 const float* __restrict__ r,
                                 float* __restrict__ z,
                                 int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n && diag[i] != 0.0f) {
        z[i] = r[i] / diag[i];
    } else if (i < n) {
        z[i] = r[i];
    }
}

__global__ void pcg_update_x_r_kernel(CGState state,
                                      float alpha,
                                      int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;

    state.x[i] += alpha * state.p[i];
    state.r[i] -= alpha * state.Ap[i];
}

__global__ void pcg_update_beta_p_kernel(CGState state,
                                         const float* __restrict__ z,
                                         float rz_new,
                                         float rz_old,
                                         int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;

    float beta = (rz_old > 0) ? rz_new / rz_old : 0.0f;
    state.p[i] = z[i] + beta * state.p[i];
}

// ============================================================================
// ADMM Solver (for L1-regularized problems)
// ============================================================================

__global__ void admm_x_update_kernel(const float* __restrict__ A,
                                     const float* __restrict__ b,
                                     const float* __restrict__ z,
                                     const float* __restrict__ u,
                                     float* __restrict__ x,
                                     float rho,
                                     int m, int n) {
    // x = (A^T A + rho I)^-1 (A^T b + rho (z - u))
    // Simplified: using diagonal approximation
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;

    // Compute A^T A diagonal
    float ata_diag = 0.0f;
    for (int row = 0; row < m; ++row) {
        float a = A[row * n + i];
        ata_diag += a * a;
    }

    // Compute A^T b
    float atb = 0.0f;
    for (int row = 0; row < m; ++row) {
        atb += A[row * n + i] * b[row];
    }

    float denom = ata_diag + rho;
    x[i] = (atb + rho * (z[i] - u[i])) / denom;
}

__global__ void admm_z_update_kernel(const float* __restrict__ x,
                                     const float* __restrict__ u,
                                     float* __restrict__ z,
                                     const float* __restrict__ lambda,
                                     float rho,
                                     int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;

    float v = x[i] + u[i];
    float threshold = lambda[i] / rho;

    if (v > threshold) {
        z[i] = v - threshold;
    } else if (v < -threshold) {
        z[i] = v + threshold;
    } else {
        z[i] = 0.0f;
    }
}

__global__ void admm_u_update_kernel(const float* __restrict__ x,
                                     const float* __restrict__ z,
                                     float* __restrict__ u,
                                     float alpha,
                                     int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;

    u[i] += alpha * (x[i] - z[i]);
}

__global__ void admm_check_convergence_kernel(const float* __restrict__ x,
                                              const float* __restrict__ z,
                                              const float* __restrict__ u,
                                              const float* __restrict__ x_prev,
                                              float* primal_residual,
                                              float* dual_residual,
                                              float rho,
                                              int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float primal = 0.0f;
    float dual = 0.0f;

    while (i < n) {
        float diff = x[i] - z[i];
        primal += diff * diff;

        float diff_z = z[i] - x_prev[i];
        dual += diff_z * diff_z;

        i += blockDim.x * gridDim.x;
    }

    sdata[tid] = primal;
    sdata[tid + blockDim.x] = dual;
    __syncthreads();

    // Reduction
    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] += sdata[tid + s];
            sdata[tid + blockDim.x] += sdata[tid + s + blockDim.x];
        }
        __syncthreads();
    }

    if (tid == 0) {
        *primal_residual = sqrtf(sdata[0]);
        *dual_residual = rho * sqrtf(sdata[blockDim.x]);
    }
}

// ============================================================================
// Regularized Least Squares (RLS)
// ============================================================================

__global__ void rls_form_normal_equations_kernel(const float* __restrict__ A,
                                                 const float* __restrict__ b,
                                                 float* __restrict__ ATA,
                                                 float* __restrict__ ATb,
                                                 int m, int n) {
    int i = blockIdx.y * blockDim.y + threadIdx.y;
    int j = blockIdx.x * blockDim.x + threadIdx.x;

    if (i >= n || j >= n) return;

    // Compute ATA[i,j] = sum_k A[k,i] * A[k,j]
    float sum = 0.0f;
    for (int k = 0; k < m; ++k) {
        sum += A[k * n + i] * A[k * n + j];
    }
    ATA[i * n + j] = sum;

    if (i == j) {
        // Also compute diagonal of ATb
        float sum_b = 0.0f;
        for (int k = 0; k < m; ++k) {
            sum_b += A[k * n + i] * b[k];
        }
        ATb[i] = sum_b;
    }
}

__global__ void rls_add_regularization_kernel(float* __restrict__ ATA,
                                              float* __restrict__ lambda,
                                              int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        ATA[i * n + i] += lambda[i];
    }
}

__global__ void rls_solve_cholesky_kernel(const float* __restrict__ ATA,
                                          const float* __restrict__ ATb,
                                          float* __restrict__ x,
                                          int n) {
    // Simplified: diagonal solve (Jacobi)
    // Full Cholesky would require more complex kernel
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        x[i] = ATb[i] / ATA[i * n + i];
    }
}

// ============================================================================
// Host Solver Classes
// ============================================================================

class ConjugateGradientSolver {
public:
    ConjugateGradientSolver(bool use_sparse = true) : use_sparse_(use_sparse) {}

    void solve(const float* A_dense,          // Dense matrix [n x n]
               const int* row_ptr,            // CSR row pointer
               const int* col_idx,            // CSR col indices
               const float* values,           // CSR values
               const float* b,
               float* x,
               int n,
               int max_iter = 1000,
               float tol = 1e-6f) {

        CGState state;
        state.allocate(n);
        state.max_iterations = max_iter;
        state.tolerance = tol;

        // Initialize
        dim3 block(256);
        dim3 grid((n + 255) / 256);

        // x = 0, r = b, p = r
        cudaMemset(state.x, 0, n * sizeof(float));
        cudaMemcpy(state.r, b, n * sizeof(float), cudaMemcpyDeviceToDevice);
        cudaMemcpy(state.p, b, n * sizeof(float), cudaMemcpyDeviceToDevice);

        float* d_rz_old;
        float* d_rz_new;
        cudaMalloc(&d_rz_old, sizeof(float));
        cudaMalloc(&d_rz_new, sizeof(float));

        // Initial r^T r
        cudaMemset(d_rz_old, 0, sizeof(float));
        dot_product_kernel<<<grid, block, block.x * sizeof(float)>>>(state.r, state.r, d_rz_old, n);
        cudaDeviceSynchronize();

        for (int iter = 0; iter < max_iter; ++iter) {
            state.iterations = iter;

            // Ap = A * p
            if (use_sparse_ && row_ptr) {
                spmv_csr_kernel<<<grid, block>>>(row_ptr, col_idx, values, state.p, state.Ap, n);
            } else {
                gemv_kernel<<<grid, block>>>(A_dense, state.p, state.Ap, n, n);
            }
            cudaDeviceSynchronize();

            // alpha = r^T r / p^T Ap
            float h_rz_old;
            cudaMemcpy(&h_rz_old, d_rz_old, sizeof(float), cudaMemcpyDeviceToHost);

            cudaMemset(d_rz_new, 0, sizeof(float));
            dot_product_kernel<<<grid, block, block.x * sizeof(float)>>>(state.p, state.Ap, d_rz_new, n);
            cudaDeviceSynchronize();

            float h_pAp;
            cudaMemcpy(&h_pAp, d_rz_new, sizeof(float), cudaMemcpyDeviceToHost);

            float alpha = (h_pAp > 0) ? h_rz_old / h_pAp : 0.0f;

            // x = x + alpha * p
            // r = r - alpha * Ap
            cg_update_x_r_kernel<<<grid, block>>>(state, alpha, n);
            cudaDeviceSynchronize();

            // Check convergence
            cudaMemset(d_rz_new, 0, sizeof(float));
            dot_product_kernel<<<grid, block, block.x * sizeof(float)>>>(state.r, state.r, d_rz_new, n);
            cudaDeviceSynchronize();

            float h_rz_new;
            cudaMemcpy(&h_rz_new, d_rz_new, sizeof(float), cudaMemcpyDeviceToHost);
            state.residual_norm = sqrtf(h_rz_new);

            if (state.residual_norm < tol) {
                state.converged = true;
                break;
            }

            // beta = r_new^T r_new / r_old^T r_old
            float beta = (h_rz_old > 0) ? h_rz_new / h_rz_old : 0.0f;

            // p = r + beta * p
            cg_update_beta_p_kernel<<<grid, block>>>(state, beta, n);
            cudaDeviceSynchronize();

            // Swap rz_old and rz_new
            std::swap(d_rz_old, d_rz_new);
        }

        // Copy result
        cudaMemcpy(x, state.x, n * sizeof(float), cudaMemcpyDeviceToDevice);

        state.free();
        cudaFree(d_rz_old);
        cudaFree(d_rz_new);
    }

private:
    bool use_sparse_;
};

class ADMMSolver {
public:
    ADMMSolver() {}

    void solve(const float* A_dense,
               const float* b,
               const float* lambda,       // Regularization vector [n]
               float* x,
               int m, int n,
               int max_iter = 1000,
               float primal_tol = 1e-4f,
               float dual_tol = 1e-4f,
               float rho = 1.0f) {

        ADMMState state;
        state.allocate(n);
        state.max_iterations = max_iter;
        state.primal_tol = primal_tol;
        state.dual_tol = dual_tol;
        state.rho = rho;

        dim3 block(256);
        dim3 grid((n + 255) / 256);

        // Initialize
        cudaMemset(state.x, 0, n * sizeof(float));
        cudaMemset(state.z, 0, n * sizeof(float));
        cudaMemset(state.u, 0, n * sizeof(float));

        float* d_primal_res;
        float* d_dual_res;
        cudaMalloc(&d_primal_res, sizeof(float));
        cudaMalloc(&d_dual_res, sizeof(float));

        for (int iter = 0; iter < max_iter; ++iter) {
            state.iterations = iter;

            // x-update
            admm_x_update_kernel<<<grid, block>>>(A_dense, b, state.z, state.u,
                                                   state.x, rho, m, n);
            cudaDeviceSynchronize();

            // z-update
            admm_z_update_kernel<<<grid, block>>>(state.x, state.u, state.z, lambda, rho, n);
            cudaDeviceSynchronize();

            // u-update
            admm_u_update_kernel<<<grid, block>>>(state.x, state.z, state.u, 1.0f, n);
            cudaDeviceSynchronize();

            // Check convergence
            cudaMemcpy(state.x_prev, state.x, n * sizeof(float), cudaMemcpyDeviceToDevice);

            admm_check_convergence_kernel<<<1, block, 2 * block.x * sizeof(float)>>>(
                state.x, state.z, state.u, state.x_prev,
                d_primal_res, d_dual_res, rho, n);
            cudaDeviceSynchronize();

            float h_primal, h_dual;
            cudaMemcpy(&h_primal, d_primal_res, sizeof(float), cudaMemcpyDeviceToHost);
            cudaMemcpy(&h_dual, d_dual_res, sizeof(float), cudaMemcpyDeviceToHost);

            state.primal_residual = h_primal;
            state.dual_residual = h_dual;

            if (h_primal < primal_tol && h_dual < dual_tol) {
                state.converged = true;
                break;
            }
        }

        cudaMemcpy(x, state.x, n * sizeof(float), cudaMemcpyDeviceToDevice);

        state.free();
        cudaFree(d_primal_res);
        cudaFree(d_dual_res);
    }
};

class RLSSolver {
public:
    RLSSolver() {}

    void solve(const float* A_dense,
               const float* b,
               const float* lambda,
               float* x,
               int m, int n) {

        RLSState state;
        state.allocate(m, n);

        // Copy A and b
        cudaMemcpy(state.A, A_dense, m * n * sizeof(float), cudaMemcpyDeviceToDevice);
        cudaMemcpy(state.b, b, m * sizeof(float), cudaMemcpyDeviceToDevice);
        cudaMemcpy(state.lambda, lambda, n * sizeof(float), cudaMemcpyDeviceToDevice);

        dim3 block(16, 16);
        dim3 grid((n + 15) / 16, (n + 15) / 16);

        // Form ATA and ATb
        rls_form_normal_equations_kernel<<<grid, block>>>(state.A, state.b, state.ATA, state.ATb, m, n);
        cudaDeviceSynchronize();

        // Add regularization to diagonal
        int vec_block = 256;
        int vec_grid = (n + vec_block - 1) / vec_block;
        rls_add_regularization_kernel<<<vec_grid, vec_block>>>(state.ATA, state.lambda, n);
        cudaDeviceSynchronize();

        // Solve (simplified diagonal)
        rls_solve_cholesky_kernel<<<vec_grid, vec_block>>>(state.ATA, state.ATb, state.x, n);
        cudaDeviceSynchronize();

        cudaMemcpy(x, state.x, n * sizeof(float), cudaMemcpyDeviceToDevice);

        state.free();
    }
};

} // namespace cauveris