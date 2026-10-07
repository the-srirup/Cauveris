#include "cauveris/kernel_types.h"
#include <cmath>

namespace cauveris {

__global__ void conjugate_gradient_kernel(
    const float* A,           // Kernel matrix [n_obs * n_comp * n_time]
    const float* b,           // Measurements [n_obs * n_time]
    float* x,                 // Solution [n_comp * n_time]
    float* r,                 // Residual [n_obs * n_time]
    float* p,                 // Search direction [n_comp * n_time]
    float* Ap,                // A*p [n_obs * n_time]
    float* alpha,
    float* beta,
    int n_comp,
    int n_obs,
    int n_time,
    float reg
) {
    int tid = threadIdx.x;
    int bid = blockIdx.x;

    // This is a simplified single-block implementation
    // For production, use multi-block with shared memory

    if (bid == 0 && tid == 0) {
        // Initialize r = b - A*x
        for (int i = 0; i < n_obs * n_time; ++i) {
            r[i] = b[i];
            float sum = 0.0f;
            for (int j = 0; j < n_comp * n_time; ++j) {
                sum += A[i * (n_comp * n_time) + j] * x[j];
            }
            r[i] -= sum;
        }

        // Initialize p = r (projected to solution space)
        for (int j = 0; j < n_comp * n_time; ++j) {
            float sum = 0.0f;
            for (int i = 0; i < n_obs; ++i) {
                sum += A[i * (n_comp * n_time) + j] * r[i * n_time + 0]; // Simplified
            }
            p[j] = sum;
        }
    }

    __syncthreads();

    // Single-threaded CG iterations for simplicity
    if (tid == 0 && bid == 0) {
        float rTr = 0.0f;
        for (int i = 0; i < n_obs * n_time; ++i) rTr += r[i] * r[i];

        for (int iter = 0; iter < 100; ++iter) {
            // Ap = A * p
            for (int i = 0; i < n_obs * n_time; ++i) {
                Ap[i] = 0.0f;
                for (int j = 0; j < n_comp * n_time; ++j) {
                    Ap[i] += A[i * (n_comp * n_time) + j] * p[j];
                }
                // Add regularization
                if (i < n_comp * n_time) Ap[i] += reg * p[i];
            }

            float pTAp = 0.0f;
            for (int j = 0; j < n_comp * n_time; ++j) pTAp += p[j] * Ap[j]; // Simplified

            *alpha = rTr / (pTAp + 1e-8f);

            // x = x + alpha * p
            for (int j = 0; j < n_comp * n_time; ++j) {
                x[j] += *alpha * p[j];
            }

            // r = r - alpha * Ap
            float new_rTr = 0.0f;
            for (int i = 0; i < n_obs * n_time; ++i) {
                r[i] -= *alpha * Ap[i];
                new_rTr += r[i] * r[i];
            }

            if (sqrtf(new_rTr) < 1e-6f) break;

            *beta = new_rTr / rTr;
            rTr = new_rTr;

            // p = r + beta * p (projected)
            for (int j = 0; j < n_comp * n_time; ++j) {
                float r_proj = 0.0f;
                for (int i = 0; i < n_obs; ++i) {
                    r_proj += A[i * (n_comp * n_time) + j] * r[i * n_time];
                }
                p[j] = r_proj + *beta * p[j];
            }
        }
    }
}

__global__ void regularized_least_squares_kernel(
    const float* K,       // [n_obs * n_comp * n_time]
    const float* y,       // [n_obs * n_time]
    float* x,             // [n_comp * n_time]
    int n_comp,
    int n_obs,
    int n_time,
    float lambda
) {
    // Solve (K^T K + lambda I) x = K^T y
    // Using normal equations with Tikhonov regularization

    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int total = n_comp * n_time;
    if (idx >= total) return;

    // Compute K^T y
    float KTy = 0.0f;
    for (int i = 0; i < n_obs * n_time; ++i) {
        KTy += K[i * total + idx] * y[i];
    }

    // Compute (K^T K)_{idx, idx}
    float KTK_diag = lambda;
    for (int i = 0; i < n_obs * n_time; ++i) {
        KTK_diag += K[i * total + idx] * K[i * total + idx];
    }

    // Diagonal approximation
    x[idx] = KTy / KTK_diag;
}

__global__ void admm_solver_kernel(
    const float* K,       // [n_obs * n_comp * n_time]
    const float* b,       // [n_obs * n_time]
    float* x,             // [n_comp * n_time]
    float* z,             // Auxiliary variable
    float* u,             // Dual variable
    int n_comp,
    int n_obs,
    int n_time,
    float rho,
    float lambda,
    int max_iter
) {
    int tid = threadIdx.x;
    if (tid == 0) {
        int total = n_comp * n_time;

        for (int iter = 0; iter < max_iter; ++iter) {
            // x-update: solve (K^T K + rho I) x = K^T b + rho (z - u)
            for (int j = 0; j < total; ++j) {
                float KTK_rho = rho;
                for (int i = 0; i < n_obs * n_time; ++i) {
                    KTK_rho += K[i * total + j] * K[i * total + j];
                }

                float rhs = rho * (z[j] - u[j]);
                for (int i = 0; i < n_obs * n_time; ++i) {
                    rhs += K[i * total + j] * b[i];
                }

                x[j] = rhs / KTK_rho;
            }

            // z-update: soft thresholding
            for (int j = 0; j < total; ++j) {
                float val = x[j] + u[j];
                if (val > lambda / rho) z[j] = val - lambda / rho;
                else if (val < -lambda / rho) z[j] = val + lambda / rho;
                else z[j] = 0.0f;
            }

            // u-update
            for (int j = 0; j < total; ++j) {
                u[j] += x[j] - z[j];
            }
        }
    }
}

__global__ void compute_residual_kernel(
    const float* K,
    const float* x,
    const float* b,
    float* residual,
    int n_comp,
    int n_obs,
    int n_time
) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    int total_obs = n_obs * n_time;
    if (i >= total_obs) return;

    int total_x = n_comp * n_time;
    float pred = 0.0f;
    for (int j = 0; j < total_x; ++j) {
        pred += K[i * total_x + j] * x[j];
    }
    residual[i] = b[i] - pred;
}

__global__ void compute_residual_norm_kernel(
    const float* residual,
    float* norm,
    int n
) {
    extern __shared__ float sdata[];
    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float val = (i < n) ? residual[i] * residual[i] : 0.0f;
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