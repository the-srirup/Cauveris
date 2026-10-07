/**
 * GPU Capability Test for Cauveris Kernels.
 */

#include <cuda_runtime.h>
#include <cuda_fp16.h>
#include <cstdio>
#include <cstdlib>

int main() {
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);

    if (err != cudaSuccess) {
        printf("CUDA Error: %s\n", cudaGetErrorString(err));
        return 1;
    }

    if (device_count == 0) {
        printf("No CUDA devices found\n");
        return 1;
    }

    printf("Found %d CUDA device(s)\n", device_count);

    for (int i = 0; i < device_count; ++i) {
        cudaDeviceProp prop;
        cudaGetDeviceProperties(&prop, i);

        printf("\nDevice %d: %s\n", i, prop.name);
        printf("  Compute Capability: %d.%d\n", prop.major, prop.minor);
        printf("  Total Global Memory: %.2f GB\n", prop.totalGlobalMem / (1024.0 * 1024.0 * 1024.0));
        printf("  Multiprocessors: %d\n", prop.multiProcessorCount);
        printf("  Max Threads per Block: %d\n", prop.maxThreadsPerBlock);
        printf("  Max Threads per SM: %d\n", prop.maxThreadsPerMultiProcessor);
        printf("  Warp Size: %d\n", prop.warpSize);
        printf("  Clock Rate: %.2f GHz\n", prop.clockRate / 1e6);
        printf("  Memory Clock: %.2f GHz\n", prop.memoryClockRate / 1e6);
        printf("  Memory Bus Width: %d-bit\n", prop.memoryBusWidth);
        printf("  Tensor Cores: %s\n", (prop.major >= 7) ? "Yes" : "No");
        printf("  Async Copy: %s\n", (prop.major >= 8) ? "Yes" : "No");
        printf("  Unified Memory: %s\n", prop.unifiedAddressing ? "Yes" : "No");
        printf("  Max Shared Memory per Block: %zu KB\n", prop.sharedMemPerBlock / 1024);
        printf("  Registers per Block: %d\n", prop.regsPerBlock);

        // Test basic kernel launch
        cudaSetDevice(i);

        // Simple kernel test
        const int N = 1024;
        float *d_a, *d_b, *d_c;
        cudaMalloc(&d_a, N * sizeof(float));
        cudaMalloc(&d_b, N * sizeof(float));
        cudaMalloc(&d_c, N * sizeof(float));

        // Initialize
        float* h_a = new float[N];
        float* h_b = new float[N];
        for (int j = 0; j < N; ++j) {
            h_a[j] = static_cast<float>(j) * 0.1f;
            h_b[j] = static_cast<float>(j) * 0.2f;
        }
        cudaMemcpy(d_a, h_a, N * sizeof(float), cudaMemcpyHostToDevice);
        cudaMemcpy(d_b, h_b, N * sizeof(float), cudaMemcpyHostToDevice);

        // Launch simple add kernel
        dim3 block(256);
        dim3 grid((N + 255) / 256);

        __global__ void add_kernel(const float* a, const float* b, float* c, int n) {
            int i = blockIdx.x * blockDim.x + threadIdx.x;
            if (i < n) c[i] = a[i] + b[i];
        }

        add_kernel<<<grid, block>>>(d_a, d_b, d_c, N);
        cudaDeviceSynchronize();

        // Verify
        float* h_c = new float[N];
        cudaMemcpy(h_c, d_c, N * sizeof(float), cudaMemcpyDeviceToHost);

        bool pass = true;
        for (int j = 0; j < N; ++j) {
            float expected = h_a[j] + h_b[j];
            if (fabsf(h_c[j] - expected) > 1e-5f) {
                printf("  Mismatch at %d: got %f, expected %f\n", j, h_c[j], expected);
                pass = false;
                break;
            }
        }

        if (pass) {
            printf("  Kernel test: PASSED\n");
        } else {
            printf("  Kernel test: FAILED\n");
            return 1;
        }

        // Test FP16
        if (prop.major >= 7) {
            half *d_a16, *d_b16, *d_c16;
            cudaMalloc(&d_a16, N * sizeof(half));
            cudaMalloc(&d_b16, N * sizeof(half));
            cudaMalloc(&d_c16, N * sizeof(half));

            __global__ void add_fp16_kernel(const half* a, const half* b, half* c, int n) {
                int i = blockIdx.x * blockDim.x + threadIdx.x;
                if (i < n) c[i] = __hadd(a[i], b[i]);
            }

            // Convert to FP16
            half* h_a16 = new half[N];
            half* h_b16 = new half[N];
            for (int j = 0; j < N; ++j) {
                h_a16[j] = __float2half_rn(h_a[j]);
                h_b16[j] = __float2half_rn(h_b[j]);
            }
            cudaMemcpy(d_a16, h_a16, N * sizeof(half), cudaMemcpyHostToDevice);
            cudaMemcpy(d_b16, h_b16, N * sizeof(half), cudaMemcpyHostToDevice);

            add_fp16_kernel<<<grid, block>>>(d_a16, d_b16, d_c16, N);
            cudaDeviceSynchronize();

            half* h_c16 = new half[N];
            cudaMemcpy(h_c16, d_c16, N * sizeof(half), cudaMemcpyDeviceToHost);

            bool fp16_pass = true;
            for (int j = 0; j < N; ++j) {
                float expected = __half2float(h_a16[j]) + __half2float(h_b16[j]);
                float got = __half2float(h_c16[j]);
                if (fabsf(got - expected) > 1e-3f) {
                    printf("  FP16 Mismatch at %d: got %f, expected %f\n", j, got, expected);
                    fp16_pass = false;
                    break;
                }
            }

            if (fp16_pass) {
                printf("  FP16 test: PASSED\n");
            } else {
                printf("  FP16 test: FAILED\n");
            }

            delete[] h_a16;
            delete[] h_b16;
            delete[] h_c16;
            cudaFree(d_a16);
            cudaFree(d_b16);
            cudaFree(d_c16);
        }

        delete[] h_a;
        delete[] h_b;
        delete[] h_c;
        cudaFree(d_a);
        cudaFree(d_b);
        cudaFree(d_c);
    }

    printf("\nAll tests passed!\n");
    return 0;
}