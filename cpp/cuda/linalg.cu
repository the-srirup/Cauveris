/**
 * Linear algebra primitives and iterative solvers.
 *
 * Every entry point takes HOST pointers and moves the data to the device
 * itself, so a caller can never hand a host array to a kernel by mistake.
 * That mistake is silent: the pointer is a perfectly valid device address,
 * it just does not point at the data, and the kernel reads whatever happens
 * to live there.
 */

#include "cauveris/linalg.h"

#include <cuda_runtime.h>

#include <cmath>
#include <cstring>
#include <vector>

#include "cauveris/cuda_utils.h"

namespace cauveris {
namespace {

constexpr int kBlockSize = 256;

__global__ void matmul_kernel(const float* __restrict__ A,
                              const float* __restrict__ B,
                              float* __restrict__ C,
                              int m, int n, int k) {
    const int row = blockIdx.y * blockDim.y + threadIdx.y;
    const int col = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= m || col >= n) {
        return;
    }
    float sum = 0.0f;
    for (int i = 0; i < k; ++i) {
        sum += A[row * k + i] * B[i * n + col];
    }
    C[row * n + col] = sum;
}

__global__ void batch_matmul_kernel(const float* __restrict__ A,
                                    const float* __restrict__ B,
                                    float* __restrict__ C,
                                    int batch, int m, int n, int k) {
    const int b = blockIdx.z;
    const int row = blockIdx.y * blockDim.y + threadIdx.y;
    const int col = blockIdx.x * blockDim.x + threadIdx.x;
    if (b >= batch || row >= m || col >= n) {
        return;
    }
    const float* a = A + static_cast<size_t>(b) * m * k;
    const float* bb = B + static_cast<size_t>(b) * k * n;
    float* c = C + static_cast<size_t>(b) * m * n;
    float sum = 0.0f;
    for (int i = 0; i < k; ++i) {
        sum += a[row * k + i] * bb[i * n + col];
    }
    c[row * n + col] = sum;
}

__global__ void dot_product_kernel(const float* __restrict__ a,
                                   const float* __restrict__ b,
                                   float* __restrict__ out,
                                   int n) {
    extern __shared__ float sdata[];
    float partial = 0.0f;
    for (int i = threadIdx.x; i < n; i += blockDim.x) {
        partial += a[i] * b[i];
    }
    sdata[threadIdx.x] = partial;
    __syncthreads();
    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (threadIdx.x < s) {
            sdata[threadIdx.x] += sdata[threadIdx.x + s];
        }
        __syncthreads();
    }
    if (threadIdx.x == 0) {
        atomicAdd(out, sdata[0]);
    }
}

__global__ void norm_kernel(const float* __restrict__ x,
                             float* __restrict__ out,
                             int n,
                             int mode) {
    // mode 0: sum of squares (the square root is taken on the host)
    // mode 1: sum of absolute values
    extern __shared__ float sdata[];
    float partial = 0.0f;
    for (int i = threadIdx.x; i < n; i += blockDim.x) {
        const float v = x[i];
        partial += (mode == 0) ? v * v : fabsf(v);
    }
    sdata[threadIdx.x] = partial;
    __syncthreads();
    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (threadIdx.x < s) {
            sdata[threadIdx.x] += sdata[threadIdx.x + s];
        }
        __syncthreads();
    }
    if (threadIdx.x == 0) {
        atomicAdd(out, sdata[0]);
    }
}

__global__ void scale_kernel(float* __restrict__ y,
                              const float* __restrict__ x,
                              float alpha,
                              int n) {
    const int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        y[i] = alpha * x[i];
    }
}

__global__ void axpy_kernel(float* __restrict__ y,
                            const float* __restrict__ x,
                            float alpha,
                            int n) {
    const int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        y[i] += alpha * x[i];
    }
}

__global__ void gemv_kernel(const float* __restrict__ A,
                            const float* __restrict__ x,
                            float* __restrict__ y,
                            int m, int n) {
    const int row = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= m) {
        return;
    }
    float sum = 0.0f;
    for (int col = 0; col < n; ++col) {
        sum += A[row * n + col] * x[col];
    }
    y[row] = sum;
}

__global__ void spmv_csr_kernel(const int* __restrict__ row_ptr,
                                const int* __restrict__ col_idx,
                                const float* __restrict__ values,
                                const float* __restrict__ x,
                                float* __restrict__ y,
                                int num_rows) {
    const int row = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= num_rows) {
        return;
    }
    float sum = 0.0f;
    const int start = row_ptr[row];
    const int end = row_ptr[row + 1];
    for (int idx = start; idx < end; ++idx) {
        sum += values[idx] * x[col_idx[idx]];
    }
    y[row] = sum;
}

// The search direction is updated in place: p = r + beta * p.  The buffer p
// is therefore both an input and the output, and it must not carry the
// __restrict__ qualifier - the compiler is allowed to assume that two
// restrict pointers do not overlap, and here they are the same pointer.
__global__ void combine_kernel(const float* __restrict__ r,
                               float* p,
                               float beta,
                               int n) {
    const int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        p[i] = r[i] + beta * p[i];
    }
}

// One row of L per launch: L = lower triangular Cholesky factor of M.
__global__ void cholesky_column_kernel(const float* __restrict__ M,
                                       float* __restrict__ L,
                                       int n,
                                       int col) {
    extern __shared__ float s_diag[];

    if (threadIdx.x == 0) {
        float sum = M[col * n + col];
        for (int k = 0; k < col; ++k) {
            sum -= L[col * n + k] * L[col * n + k];
        }
        // A non-positive pivot means the matrix is not positive definite.
        // The factorization cannot continue; 1.0 keeps the arithmetic
        // finite and the caller sees the failure through the residual.
        const float diag = (sum > 0.0f) ? sqrtf(sum) : 1.0f;
        L[col * n + col] = diag;
        s_diag[0] = diag;
    }
    __syncthreads();

    const float diag = s_diag[0];
    for (int row = col + 1 + static_cast<int>(threadIdx.x); row < n;
         row += static_cast<int>(blockDim.x)) {
        float sum = M[row * n + col];
        for (int k = 0; k < col; ++k) {
            sum -= L[row * n + k] * L[col * n + k];
        }
        L[row * n + col] = sum / diag;
    }
}

// Normal equations of a least squares problem: ATA and ATb.
__global__ void normal_equations_kernel(const float* __restrict__ A,
                                         const float* __restrict__ b,
                                         float* __restrict__ ata,
                                         float* __restrict__ atb,
                                         int m, int n) {
    const int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) {
        return;
    }
    float atb_i = 0.0f;
    for (int k = 0; k < m; ++k) {
        atb_i += A[k * n + i] * b[k];
    }
    atb[i] = atb_i;

    for (int j = blockIdx.y; j < n; j += gridDim.y) {
        float sum = 0.0f;
        for (int k = 0; k < m; ++k) {
            sum += A[k * n + i] * A[k * n + j];
        }
        ata[i * n + j] = sum;
    }
}

__global__ void add_diagonal_kernel(float* __restrict__ matrix,
                                    const float* __restrict__ diagonal,
                                    int n) {
    const int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        matrix[i * n + i] += diagonal[i];
    }
}

// Copy a device matrix to the host.
void copy_device_to_host(const float* d_src, float* h_dst, size_t count) {
    CAUVERIS_CUDA_CHECK(cudaMemcpy(h_dst, d_src, count * sizeof(float), cudaMemcpyDeviceToHost));
}

}  // namespace

void matmul(const float* A, const float* B, float* C, int m, int n, int k) {
    if (m <= 0 || n <= 0 || k <= 0) {
        return;
    }
    float *dA = nullptr, *dB = nullptr, *dC = nullptr;
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dA, static_cast<size_t>(m) * k * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dB, static_cast<size_t>(k) * n * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dC, static_cast<size_t>(m) * n * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dA, A, static_cast<size_t>(m) * k * sizeof(float),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dB, B, static_cast<size_t>(k) * n * sizeof(float),
                                   cudaMemcpyHostToDevice));

    dim3 block(16, 16);
    dim3 grid((n + 15) / 16, (m + 15) / 16);
    matmul_kernel<<<grid, block>>>(dA, dB, dC, m, n, k);
    CAUVERIS_CUDA_CHECK_KERNEL();

    copy_device_to_host(dC, C, static_cast<size_t>(m) * n);
    CAUVERIS_CUDA_CHECK(cudaFree(dA));
    CAUVERIS_CUDA_CHECK(cudaFree(dB));
    CAUVERIS_CUDA_CHECK(cudaFree(dC));
}

void batch_matmul(const float* A, const float* B, float* C, int batch, int m, int n, int k) {
    if (batch <= 0 || m <= 0 || n <= 0 || k <= 0) {
        return;
    }
    const size_t a_count = static_cast<size_t>(batch) * m * k;
    const size_t b_count = static_cast<size_t>(batch) * k * n;
    const size_t c_count = static_cast<size_t>(batch) * m * n;

    float *dA = nullptr, *dB = nullptr, *dC = nullptr;
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dA, a_count * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dB, b_count * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dC, c_count * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dA, A, a_count * sizeof(float), cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dB, B, b_count * sizeof(float), cudaMemcpyHostToDevice));

    dim3 block(16, 16);
    dim3 grid((n + 15) / 16, (m + 15) / 16, batch);
    batch_matmul_kernel<<<grid, block>>>(dA, dB, dC, batch, m, n, k);
    CAUVERIS_CUDA_CHECK_KERNEL();

    copy_device_to_host(dC, C, c_count);
    CAUVERIS_CUDA_CHECK(cudaFree(dA));
    CAUVERIS_CUDA_CHECK(cudaFree(dB));
    CAUVERIS_CUDA_CHECK(cudaFree(dC));
}

float dot_product(const float* a, const float* b, int n) {
    if (n <= 0) {
        return 0.0f;
    }
    float *da = nullptr, *db = nullptr, *dout = nullptr;
    CAUVERIS_CUDA_CHECK(cudaMalloc(&da, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&db, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dout, sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(da, a, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(db, b, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemset(dout, 0, sizeof(float)));

    dot_product_kernel<<<1, kBlockSize, kBlockSize * sizeof(float)>>>(da, db, dout, n);
    CAUVERIS_CUDA_CHECK_KERNEL();

    float result = 0.0f;
    CAUVERIS_CUDA_CHECK(cudaMemcpy(&result, dout, sizeof(float), cudaMemcpyDeviceToHost));
    CAUVERIS_CUDA_CHECK(cudaFree(da));
    CAUVERIS_CUDA_CHECK(cudaFree(db));
    CAUVERIS_CUDA_CHECK(cudaFree(dout));
    return result;
}

namespace {

float vector_norm(const float* x, int n, int mode) {
    if (n <= 0) {
        return 0.0f;
    }
    float *dx = nullptr, *dout = nullptr;
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dx, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dout, sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dx, x, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemset(dout, 0, sizeof(float)));

    norm_kernel<<<1, kBlockSize, kBlockSize * sizeof(float)>>>(dx, dout, n, mode);
    CAUVERIS_CUDA_CHECK_KERNEL();

    float result = 0.0f;
    CAUVERIS_CUDA_CHECK(cudaMemcpy(&result, dout, sizeof(float), cudaMemcpyDeviceToHost));
    CAUVERIS_CUDA_CHECK(cudaFree(dx));
    CAUVERIS_CUDA_CHECK(cudaFree(dout));
    return (mode == 0) ? sqrtf(result) : result;
}

}  // namespace

float l2_norm(const float* x, int n) {
    return vector_norm(x, n, 0);
}

float l1_norm(const float* x, int n) {
    return vector_norm(x, n, 1);
}

void scale_vector(float* y, const float* x, float alpha, int n) {
    if (n <= 0) {
        return;
    }
    float *dx = nullptr, *dy = nullptr;
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dx, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dy, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dx, x, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyHostToDevice));

    const int blocks = (n + kBlockSize - 1) / kBlockSize;
    scale_kernel<<<blocks, kBlockSize>>>(dy, dx, alpha, n);
    CAUVERIS_CUDA_CHECK_KERNEL();

    copy_device_to_host(dy, y, static_cast<size_t>(n));
    CAUVERIS_CUDA_CHECK(cudaFree(dx));
    CAUVERIS_CUDA_CHECK(cudaFree(dy));
}

void axpy(float* y, const float* x, float alpha, int n) {
    if (n <= 0) {
        return;
    }
    float *dx = nullptr, *dy = nullptr;
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dx, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dy, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dx, x, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dy, y, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyHostToDevice));

    const int blocks = (n + kBlockSize - 1) / kBlockSize;
    axpy_kernel<<<blocks, kBlockSize>>>(dy, dx, alpha, n);
    CAUVERIS_CUDA_CHECK_KERNEL();

    copy_device_to_host(dy, y, static_cast<size_t>(n));
    CAUVERIS_CUDA_CHECK(cudaFree(dx));
    CAUVERIS_CUDA_CHECK(cudaFree(dy));
}

SolverResult solve_conjugate_gradient(const float* A_dense,
                                       const int* row_ptr,
                                       const int* col_idx,
                                       const float* values,
                                       const float* b,
                                       int n,
                                       int max_iter,
                                       float tol) {
    SolverResult result;
    result.x.assign(static_cast<size_t>(n), 0.0f);
    if (n <= 0) {
        return result;
    }
    if (A_dense == nullptr && row_ptr == nullptr) {
        return result;
    }

    const bool use_sparse = (A_dense == nullptr && row_ptr != nullptr);
    if (use_sparse && (col_idx == nullptr || values == nullptr)) {
        return result;
    }

    float *db = nullptr, *dx = nullptr, *dr = nullptr, *dp = nullptr, *dAp = nullptr;
    float* d_scratch = nullptr;
    int* d_row_ptr = nullptr;
    int* d_col_idx = nullptr;
    float* d_values = nullptr;

    CAUVERIS_CUDA_CHECK(cudaMalloc(&db, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dx, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dr, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dp, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dAp, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_scratch, sizeof(float)));

    CAUVERIS_CUDA_CHECK(cudaMemcpy(db, b, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyHostToDevice));

    float* dA_dense = nullptr;
    if (!use_sparse) {
        CAUVERIS_CUDA_CHECK(cudaMalloc(&dA_dense, static_cast<size_t>(n) * n * sizeof(float)));
        CAUVERIS_CUDA_CHECK(cudaMemcpy(dA_dense, A_dense, static_cast<size_t>(n) * n * sizeof(float),
                                       cudaMemcpyHostToDevice));
    } else {
        const int nnz = row_ptr[n];
        if (nnz < 0) {
            CAUVERIS_CUDA_CHECK(cudaFree(db));
            CAUVERIS_CUDA_CHECK(cudaFree(dx));
            CAUVERIS_CUDA_CHECK(cudaFree(dr));
            CAUVERIS_CUDA_CHECK(cudaFree(dp));
            CAUVERIS_CUDA_CHECK(cudaFree(dAp));
            CAUVERIS_CUDA_CHECK(cudaFree(d_scratch));
            return result;
        }
        CAUVERIS_CUDA_CHECK(cudaMalloc(&d_row_ptr, static_cast<size_t>(n + 1) * sizeof(int)));
        // A zero sized allocation is an error on some CUDA versions, so the
        // buffers are never smaller than one element.
        const size_t nnz_alloc = static_cast<size_t>(nnz > 0 ? nnz : 1);
        CAUVERIS_CUDA_CHECK(cudaMalloc(&d_col_idx, nnz_alloc * sizeof(int)));
        CAUVERIS_CUDA_CHECK(cudaMalloc(&d_values, nnz_alloc * sizeof(float)));
        CAUVERIS_CUDA_CHECK(cudaMemcpy(d_row_ptr, row_ptr, static_cast<size_t>(n + 1) * sizeof(int),
                                       cudaMemcpyHostToDevice));
        CAUVERIS_CUDA_CHECK(cudaMemcpy(d_col_idx, col_idx, static_cast<size_t>(nnz) * sizeof(int),
                                       cudaMemcpyHostToDevice));
        CAUVERIS_CUDA_CHECK(cudaMemcpy(d_values, values, static_cast<size_t>(nnz) * sizeof(float),
                                       cudaMemcpyHostToDevice));
    }

    const int blocks = (n + kBlockSize - 1) / kBlockSize;

    // x = 0, r = b, p = r
    CAUVERIS_CUDA_CHECK(cudaMemset(dx, 0, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dr, db, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyDeviceToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dp, db, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyDeviceToDevice));

    auto device_dot = [&](const float* a, const float* c) -> float {
        CAUVERIS_CUDA_CHECK(cudaMemset(d_scratch, 0, sizeof(float)));
        dot_product_kernel<<<1, kBlockSize, kBlockSize * sizeof(float)>>>(a, c, d_scratch, n);
        CAUVERIS_CUDA_CHECK_KERNEL();
        float value = 0.0f;
        CAUVERIS_CUDA_CHECK(cudaMemcpy(&value, d_scratch, sizeof(float), cudaMemcpyDeviceToHost));
        return value;
    };

    float rz_old = device_dot(dr, dr);
    bool converged = false;
    int iteration = 0;

    for (iteration = 0; iteration < max_iter; ++iteration) {
        if (use_sparse) {
            spmv_csr_kernel<<<blocks, kBlockSize>>>(d_row_ptr, d_col_idx, d_values, dp, dAp, n);
        } else {
            gemv_kernel<<<blocks, kBlockSize>>>(dA_dense, dp, dAp, n, n);
        }
        CAUVERIS_CUDA_CHECK_KERNEL();

        const float pAp = device_dot(dp, dAp);
        if (!(pAp > 0.0f)) {
            // The matrix is not positive definite: the search direction
            // stops being a descent direction and the iteration has to stop.
            break;
        }

        const float alpha = rz_old / pAp;
        axpy_kernel<<<blocks, kBlockSize>>>(dx, dp, alpha, n);
        CAUVERIS_CUDA_CHECK_KERNEL();
        axpy_kernel<<<blocks, kBlockSize>>>(dr, dAp, -alpha, n);
        CAUVERIS_CUDA_CHECK_KERNEL();

        const float rz_new = device_dot(dr, dr);
        const float residual = sqrtf(rz_new);
        result.residual = residual;
        if (residual < tol) {
            converged = true;
            ++iteration;
            rz_old = rz_new;
            break;
        }

        const float beta = (rz_old > 0.0f) ? rz_new / rz_old : 0.0f;
        combine_kernel<<<blocks, kBlockSize>>>(dr, dp, beta, n);
        CAUVERIS_CUDA_CHECK_KERNEL();
        rz_old = rz_new;
    }

    CAUVERIS_CUDA_CHECK(cudaMemcpy(result.x.data(), dx, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyDeviceToHost));
    result.iterations = iteration;
    result.converged = converged;

    CAUVERIS_CUDA_CHECK(cudaFree(db));
    CAUVERIS_CUDA_CHECK(cudaFree(dx));
    CAUVERIS_CUDA_CHECK(cudaFree(dr));
    CAUVERIS_CUDA_CHECK(cudaFree(dp));
    CAUVERIS_CUDA_CHECK(cudaFree(dAp));
    CAUVERIS_CUDA_CHECK(cudaFree(d_scratch));
    if (dA_dense) {
        CAUVERIS_CUDA_CHECK(cudaFree(dA_dense));
    }
    if (d_row_ptr) {
        CAUVERIS_CUDA_CHECK(cudaFree(d_row_ptr));
    }
    if (d_col_idx) {
        CAUVERIS_CUDA_CHECK(cudaFree(d_col_idx));
    }
    if (d_values) {
        CAUVERIS_CUDA_CHECK(cudaFree(d_values));
    }
    return result;
}

SolverResult solve_rls(const float* A, const float* b, const float* lambda, int m, int n) {
    SolverResult result;
    result.x.assign(static_cast<size_t>(n), 0.0f);
    if (m <= 0 || n <= 0) {
        return result;
    }

    const size_t a_count = static_cast<size_t>(m) * n;

    float *dA = nullptr, *db = nullptr, *d_ata = nullptr, *d_atb = nullptr, *d_lambda = nullptr;
    float* dL = nullptr;

    CAUVERIS_CUDA_CHECK(cudaMalloc(&dA, a_count * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&db, static_cast<size_t>(m) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_ata, static_cast<size_t>(n) * n * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&d_atb, static_cast<size_t>(n) * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMalloc(&dL, static_cast<size_t>(n) * n * sizeof(float)));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(dA, A, a_count * sizeof(float), cudaMemcpyHostToDevice));
    CAUVERIS_CUDA_CHECK(cudaMemcpy(db, b, static_cast<size_t>(m) * sizeof(float),
                                   cudaMemcpyHostToDevice));
    if (lambda != nullptr) {
        CAUVERIS_CUDA_CHECK(cudaMalloc(&d_lambda, static_cast<size_t>(n) * sizeof(float)));
        CAUVERIS_CUDA_CHECK(cudaMemcpy(d_lambda, lambda, static_cast<size_t>(n) * sizeof(float),
                                       cudaMemcpyHostToDevice));
    }

    // Normal equations.
    {
        dim3 block(kBlockSize, 1);
        dim3 grid((n + kBlockSize - 1) / kBlockSize, 16);
        normal_equations_kernel<<<grid, block>>>(dA, db, d_ata, d_atb, m, n);
        CAUVERIS_CUDA_CHECK_KERNEL();
    }
    if (d_lambda != nullptr) {
        const int blocks = (n + kBlockSize - 1) / kBlockSize;
        add_diagonal_kernel<<<blocks, kBlockSize>>>(d_ata, d_lambda, n);
        CAUVERIS_CUDA_CHECK_KERNEL();
    }

    // Cholesky factorization, one column at a time.
    const int factor_threads = (n < 512) ? ((n < 1) ? 1 : n) : 512;
    for (int col = 0; col < n; ++col) {
        cholesky_column_kernel<<<1, factor_threads, sizeof(float)>>>(d_ata, dL, n, col);
        CAUVERIS_CUDA_CHECK_KERNEL();
    }

    // The triangular solves are sequential in nature and cost O(n^2), which
    // is small next to the O(n^3) factorization, so they run on the host in
    // double precision - the arithmetic is then more accurate than the
    // single precision factorization, which is what a normal equation
    // deserves.
    std::vector<float> h_L(static_cast<size_t>(n) * n, 0.0f);
    std::vector<float> h_atb(static_cast<size_t>(n), 0.0f);
    copy_device_to_host(dL, h_L.data(), static_cast<size_t>(n) * n);
    CAUVERIS_CUDA_CHECK(cudaMemcpy(h_atb.data(), d_atb, static_cast<size_t>(n) * sizeof(float),
                                   cudaMemcpyDeviceToHost));

    std::vector<double> y(static_cast<size_t>(n), 0.0);
    for (int i = 0; i < n; ++i) {
        double sum = h_atb[i];
        for (int k = 0; k < i; ++k) {
            sum -= static_cast<double>(h_L[static_cast<size_t>(i) * n + k]) * y[k];
        }
        const double diag = h_L[static_cast<size_t>(i) * n + i];
        y[i] = (diag != 0.0) ? sum / diag : 0.0;
    }
    std::vector<double> x(static_cast<size_t>(n), 0.0);
    for (int i = n - 1; i >= 0; --i) {
        double sum = y[i];
        for (int k = i + 1; k < n; ++k) {
            sum -= static_cast<double>(h_L[static_cast<size_t>(k) * n + i]) * x[k];
        }
        const double diag = h_L[static_cast<size_t>(i) * n + i];
        x[i] = (diag != 0.0) ? sum / diag : 0.0;
    }
    for (int i = 0; i < n; ++i) {
        result.x[i] = static_cast<float>(x[i]);
    }

    // The residual of the original problem, not of the normal equations.
    {
        std::vector<float> h_x = result.x;
        std::vector<float> residual(static_cast<size_t>(m), 0.0f);
        for (int k = 0; k < m; ++k) {
            double sum = 0.0;
            for (int i = 0; i < n; ++i) {
                sum += static_cast<double>(A[static_cast<size_t>(k) * n + i]) * x[i];
            }
            residual[k] = static_cast<float>(sum - b[k]);
        }
        double norm = 0.0;
        for (float v : residual) {
            norm += static_cast<double>(v) * v;
        }
        result.residual = static_cast<float>(sqrt(norm));
    }
    result.converged = true;

    CAUVERIS_CUDA_CHECK(cudaFree(dA));
    CAUVERIS_CUDA_CHECK(cudaFree(db));
    CAUVERIS_CUDA_CHECK(cudaFree(d_ata));
    CAUVERIS_CUDA_CHECK(cudaFree(d_atb));
    CAUVERIS_CUDA_CHECK(cudaFree(dL));
    if (d_lambda != nullptr) {
        CAUVERIS_CUDA_CHECK(cudaFree(d_lambda));
    }
    return result;
}

}  // namespace cauveris
