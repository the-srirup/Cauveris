/**
 * CUDA Kernels for Matrix Operations.
 *
 * Optimized batched matrix-vector multiply, transpose multiply,
 * dot products, norms, and element-wise operations.
 */

#include "cauveris/kernel_types.h"
#include <cuda_runtime.h>
#include <cublas_v2.h>
#include <cuda_fp16.h>
#include <cstdio>

namespace cauveris {

// ============================================================================
// Batched Matrix-Vector Multiplication
// ============================================================================

__global__ void batch_gemv_kernel(const float* __restrict__ A,    // [batch, m, n]
                                  const float* __restrict__ x,    // [batch, n]
                                  float* __restrict__ y,          // [batch, m]
                                  int batch_size, int m, int n) {
    int batch = blockIdx.z;
    int row = blockIdx.y * blockDim.y + threadIdx.y;

    if (batch >= batch_size || row >= m) return;

    const float* A_batch = A + batch * m * n;
    const float* x_batch = x + batch * n;
    float* y_batch = y + batch * m;

    float sum = 0.0f;
    for (int col = 0; col < n; ++col) {
        sum += A_batch[row * n + col] * x_batch[col];
    }
    y_batch[row] = sum;
}

__global__ void batch_gemv_transpose_kernel(const float* __restrict__ A,
                                            const float* __restrict__ x,
                                            float* __restrict__ y,
                                            int batch_size, int m, int n) {
    int batch = blockIdx.z;
    int col = blockIdx.y * blockDim.y + threadIdx.y;

    if (batch >= batch_size || col >= n) return;

    const float* A_batch = A + batch * m * n;
    const float* x_batch = x + batch * m;
    float* y_batch = y + batch * n;

    float sum = 0.0f;
    for (int row = 0; row < m; ++row) {
        sum += A_batch[row * n + col] * x_batch[row];
    }
    y_batch[col] = sum;
}

// Strided batched GEMV using cuBLAS
void batch_gemv_cublas(const float* A, const float* x, float* y,
                       int batch_size, int m, int n,
                       float alpha = 1.0f, float beta = 0.0f) {
    cublasHandle_t handle;
    cublasCreate(&handle);

    // cuBLAS strided batched GEMV
    // A: [batch, m, n] column-major, so lda = m, strideA = m * n
    // x: [batch, n], incx = 1, stridex = n
    // y: [batch, m], incy = 1, stridey = m

    cublasSgemvStridedBatched(handle,
                              CUBLAS_OP_N,
                              m, n,
                              &alpha,
                              A, m, m * n,
                              x, 1, n,
                              &beta,
                              y, 1, m,
                              batch_size);

    cublasDestroy(handle);
}

// ============================================================================
// Batched Transpose
// ============================================================================

__global__ void batch_transpose_kernel(const float* __restrict__ input,  // [batch, m, n]
                                       float* __restrict__ output,       // [batch, n, m]
                                       int batch_size, int m, int n) {
    int batch = blockIdx.z;
    int row = blockIdx.y * blockDim.y + threadIdx.y;
    int col = blockIdx.x * blockDim.x + threadIdx.x;

    if (batch >= batch_size || row >= m || col >= n) return;

    output[batch * n * m + col * m + row] = input[batch * m * n + row * n + col];
}

// ============================================================================
// Element-wise Operations
// ============================================================================

__global__ void add_vectors_kernel(float* dst,
                                   const float* a,
                                   const float* b,
                                   int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = a[i] + b[i];
}

__global__ void sub_vectors_kernel(float* dst,
                                   const float* a,
                                   const float* b,
                                   int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = a[i] - b[i];
}

__global__ void mul_vectors_kernel(float* dst,
                                   const float* a,
                                   const float* b,
                                   int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = a[i] * b[i];
}

__global__ void div_vectors_kernel(float* dst,
                                   const float* a,
                                   const float* b,
                                   int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = (b[i] != 0) ? a[i] / b[i] : 0.0f;
}

__global__ void scale_vector_kernel(float* dst,
                                    const float* src,
                                    float alpha,
                                    int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = alpha * src[i];
}

__global__ void axpy_kernel(float* y,
                            const float* x,
                            float alpha,
                            int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) y[i] += alpha * x[i];
}

__global__ void clamp_kernel(float* data,
                             float min_val,
                             float max_val,
                             int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        float val = data[i];
        data[i] = fmaxf(min_val, fminf(max_val, val));
    }
}

__global__ void relu_kernel(float* data, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) data[i] = fmaxf(0.0f, data[i]);
}

__global__ void exp_kernel(float* data, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) data[i] = expf(data[i]);
}

__global__ void log_kernel(float* data, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) data[i] = (data[i] > 0) ? logf(data[i]) : 0.0f;
}

__global__ void sqrt_kernel(float* data, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) data[i] = (data[i] > 0) ? sqrtf(data[i]) : 0.0f;
}

__global__ void square_kernel(float* data, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) data[i] = data[i] * data[i];
}

__global__ void abs_kernel(float* data, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) data[i] = fabsf(data[i]);
}

// ============================================================================
// Reductions
// ============================================================================

__global__ void sum_reduce_kernel(const float* __restrict__ input,
                                  float* __restrict__ output,
                                  int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float sum = 0.0f;
    while (i < n) {
        sum += input[i];
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
        atomicAdd(output, sdata[0]);
    }
}

__global__ void max_reduce_kernel(const float* __restrict__ input,
                                  float* __restrict__ output,
                                  int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float max_val = -FLT_MAX;
    while (i < n) {
        max_val = fmaxf(max_val, input[i]);
        i += blockDim.x * gridDim.x;
    }

    sdata[tid] = max_val;
    __syncthreads();

    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] = fmaxf(sdata[tid], sdata[tid + s]);
        }
        __syncthreads();
    }

    if (tid == 0) {
        *output = fmaxf(*output, sdata[0]);
    }
}

__global__ void min_reduce_kernel(const float* __restrict__ input,
                                  float* __restrict__ output,
                                  int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float min_val = FLT_MAX;
    while (i < n) {
        min_val = fminf(min_val, input[i]);
        i += blockDim.x * gridDim.x;
    }

    sdata[tid] = min_val;
    __syncthreads();

    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] = fminf(sdata[tid], sdata[tid + s]);
        }
        __syncthreads();
    }

    if (tid == 0) {
        *output = fminf(*output, sdata[0]);
    }
}

// ============================================================================
// Dot Product
// ============================================================================

__global__ void dot_product_kernel(const float* __restrict__ a,
                                   const float* __restrict__ b,
                                   float* __restrict__ output,
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

    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] += sdata[tid + s];
        }
        __syncthreads();
    }

    if (tid == 0) {
        *output = sdata[0];
    }
}

// Batched dot product
__global__ void batch_dot_product_kernel(const float* __restrict__ a,  // [batch, n]
                                         const float* __restrict__ b,
                                         float* __restrict__ output,   // [batch]
                                         int batch_size, int n) {
    extern __shared__ float sdata[];

    int batch = blockIdx.x;
    int tid = threadIdx.x;
    int i = batch * n + tid;

    float sum = 0.0f;
    while (tid < n) {
        sum += a[i] * b[i];
        i += blockDim.x;
        tid += blockDim.x;
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
        output[batch] = sdata[0];
    }
}

// ============================================================================
// Norms
// ============================================================================

__global__ void l2_norm_kernel(const float* __restrict__ x,
                               float* __restrict__ output,
                               int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float sum = 0.0f;
    while (i < n) {
        float val = x[i];
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
        *output = sqrtf(sdata[0]);
    }
}

__global__ void l1_norm_kernel(const float* __restrict__ x,
                               float* __restrict__ output,
                               int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float sum = 0.0f;
    while (i < n) {
        sum += fabsf(x[i]);
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
        *output = sdata[0];
    }
}

__global__ void linf_norm_kernel(const float* __restrict__ x,
                                 float* __restrict__ output,
                                 int n) {
    extern __shared__ float sdata[];

    int tid = threadIdx.x;
    int i = blockIdx.x * blockDim.x + tid;

    float max_val = 0.0f;
    while (i < n) {
        max_val = fmaxf(max_val, fabsf(x[i]));
        i += blockDim.x * gridDim.x;
    }

    sdata[tid] = max_val;
    __syncthreads();

    for (int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (tid < s) {
            sdata[tid] = fmaxf(sdata[tid], sdata[tid + s]);
        }
        __syncthreads();
    }

    if (tid == 0) {
        *output = sdata[0];
    }
}

// ============================================================================
// Matrix Operations
// ============================================================================

__global__ void matmul_kernel(const float* __restrict__ A,  // [m, k]
                              const float* __restrict__ B,  // [k, n]
                              float* __restrict__ C,        // [m, n]
                              int m, int n, int k) {
    int row = blockIdx.y * blockDim.y + threadIdx.y;
    int col = blockIdx.x * blockDim.x + threadIdx.x;

    if (row >= m || col >= n) return;

    float sum = 0.0f;
    for (int i = 0; i < k; ++i) {
        sum += A[row * k + i] * B[i * n + col];
    }
    C[row * n + col] = sum;
}

__global__ void matmul_batched_kernel(const float* __restrict__ A,  // [batch, m, k]
                                      const float* __restrict__ B,  // [batch, k, n]
                                      float* __restrict__ C,        // [batch, m, n]
                                      int batch_size, int m, int n, int k) {
    int batch = blockIdx.z;
    int row = blockIdx.y * blockDim.y + threadIdx.y;
    int col = blockIdx.x * blockDim.x + threadIdx.x;

    if (batch >= batch_size || row >= m || col >= n) return;

    const float* A_batch = A + batch * m * k;
    const float* B_batch = B + batch * k * n;
    float* C_batch = C + batch * m * n;

    float sum = 0.0f;
    for (int i = 0; i < k; ++i) {
        sum += A_batch[row * k + i] * B_batch[i * n + col];
    }
    C_batch[row * n + col] = sum;
}

__global__ void outer_product_kernel(const float* __restrict__ a,  // [m]
                                     const float* __restrict__ b,  // [n]
                                     float* __restrict__ C,        // [m, n]
                                     int m, int n) {
    int row = blockIdx.y * blockDim.y + threadIdx.y;
    int col = blockIdx.x * blockDim.x + threadIdx.x;

    if (row < m && col < n) {
        C[row * n + col] = a[row] * b[col];
    }
}

// ============================================================================
// FP16 Support (Tensor Cores)
// ============================================================================

__global__ void convert_fp32_to_fp16_kernel(const float* __restrict__ input,
                                            half* __restrict__ output,
                                            int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) output[i] = __float2half_rn(input[i]);
}

__global__ void convert_fp16_to_fp32_kernel(const half* __restrict__ input,
                                            float* __restrict__ output,
                                            int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) output[i] = __half2float(input[i]);
}

// ============================================================================
// Host Wrapper Functions
// ============================================================================

void launch_batch_gemv(const float* A, const float* x, float* y,
                       int batch_size, int m, int n) {
    dim3 block(16, 16);
    dim3 grid((n + 15) / 16, (m + 15) / 16, batch_size);

    batch_gemv_kernel<<<grid, block>>>(A, x, y, batch_size, m, n);
    cudaDeviceSynchronize();
}

void launch_batch_gemv_transpose(const float* A, const float* x, float* y,
                                 int batch_size, int m, int n) {
    dim3 block(16, 16);
    dim3 grid((n + 15) / 16, (m + 15) / 16, batch_size);

    batch_gemv_transpose_kernel<<<grid, block>>>(A, x, y, batch_size, m, n);
    cudaDeviceSynchronize();
}

void launch_batch_transpose(const float* input, float* output,
                            int batch_size, int m, int n) {
    dim3 block(16, 16);
    dim3 grid((n + 15) / 16, (m + 15) / 16, batch_size);

    batch_transpose_kernel<<<grid, block>>>(input, output, batch_size, m, n);
    cudaDeviceSynchronize();
}

void launch_add_vectors(float* dst, const float* a, const float* b, int n) {
    int threads = 256;
    int blocks = (n + threads - 1) / threads;
    add_vectors_kernel<<<blocks, threads>>>(dst, a, b, n);
    cudaDeviceSynchronize();
}

void launch_scale_vector(float* dst, const float* src, float alpha, int n) {
    int threads = 256;
    int blocks = (n + threads - 1) / threads;
    scale_vector_kernel<<<blocks, threads>>>(dst, src, alpha, n);
    cudaDeviceSynchronize();
}

void launch_axpy(float* y, const float* x, float alpha, int n) {
    int threads = 256;
    int blocks = (n + threads - 1) / threads;
    axpy_kernel<<<blocks, threads>>>(y, x, alpha, n);
    cudaDeviceSynchronize();
}

void launch_clamp(float* data, float min_val, float max_val, int n) {
    int threads = 256;
    int blocks = (n + threads - 1) / threads;
    clamp_kernel<<<blocks, threads>>>(data, min_val, max_val, n);
    cudaDeviceSynchronize();
}

void launch_relu(float* data, int n) {
    int threads = 256;
    int blocks = (n + threads - 1) / threads;
    relu_kernel<<<blocks, threads>>>(data, n);
    cudaDeviceSynchronize();
}

float launch_dot_product(const float* a, const float* b, int n) {
    int threads = 256;
    int blocks = (n + threads - 1) / threads;

    float* d_result;
    cudaMalloc(&d_result, sizeof(float));
    cudaMemset(d_result, 0, sizeof(float));

    dot_product_kernel<<<blocks, threads, threads * sizeof(float)>>>(a, b, d_result, n);
    cudaDeviceSynchronize();

    float h_result;
    cudaMemcpy(&h_result, d_result, sizeof(float), cudaMemcpyDeviceToHost);
    cudaFree(d_result);

    return h_result;
}

float launch_l2_norm(const float* x, int n) {
    int threads = 256;
    int blocks = min(65535, (n + threads - 1) / threads);

    float* d_result;
    cudaMalloc(&d_result, sizeof(float));
    cudaMemset(d_result, 0, sizeof(float));

    l2_norm_kernel<<<blocks, threads, threads * sizeof(float)>>>(x, d_result, n);
    cudaDeviceSynchronize();

    float h_result;
    cudaMemcpy(&h_result, d_result, sizeof(float), cudaMemcpyDeviceToHost);
    cudaFree(d_result);

    return h_result;
}

float launch_l1_norm(const float* x, int n) {
    int threads = 256;
    int blocks = min(65535, (n + threads - 1) / threads);

    float* d_result;
    cudaMalloc(&d_result, sizeof(float));
    cudaMemset(d_result, 0, sizeof(float));

    l1_norm_kernel<<<blocks, threads, threads * sizeof(float)>>>(x, d_result, n);
    cudaDeviceSynchronize();

    float h_result;
    cudaMemcpy(&h_result, d_result, sizeof(float), cudaMemcpyDeviceToHost);
    cudaFree(d_result);

    return h_result;
}

void launch_matmul(const float* A, const float* B, float* C,
                   int m, int n, int k) {
    dim3 block(16, 16);
    dim3 grid((n + 15) / 16, (m + 15) / 16, 1);

    matmul_kernel<<<grid, block>>>(A, B, C, m, n, k);
    cudaDeviceSynchronize();
}

void launch_matmul_batched(const float* A, const float* B, float* C,
                           int batch_size, int m, int n, int k) {
    dim3 block(16, 16);
    dim3 grid((n + 15) / 16, (m + 15) / 16, batch_size);

    matmul_batched_kernel<<<grid, block>>>(A, B, C, batch_size, m, n, k);
    cudaDeviceSynchronize();
}

} // namespace cauveris