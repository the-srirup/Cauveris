/**
 * Linear algebra primitives and iterative solvers, on the GPU.
 *
 * Every entry point takes HOST pointers and is responsible for the device
 * transfers.  Handing a host pointer to a kernel is the classic way to get
 * silent garbage out of a CUDA program (the pointer is a valid address on
 * the device, it just does not point at the data), so the boundary is drawn
 * here instead of at every call site.
 */

#pragma once

#include <cstdint>
#include <vector>

namespace cauveris {

// C[m, n] = A[m, k] @ B[k, n]
void matmul(const float* A, const float* B, float* C, int m, int n, int k);

// C[batch, m, n] = A[batch, m, k] @ B[batch, k, n]
void batch_matmul(const float* A, const float* B, float* C, int batch, int m, int n, int k);

float dot_product(const float* a, const float* b, int n);
float l2_norm(const float* x, int n);
float l1_norm(const float* x, int n);

// y = alpha * x
void scale_vector(float* y, const float* x, float alpha, int n);

// y += alpha * x
void axpy(float* y, const float* x, float alpha, int n);

// The outcome of an iterative solve.
struct SolverResult {
    std::vector<float> x;
    int   iterations = 0;
    float residual   = 0.0f;   // ||b - A x||
    bool  converged  = false;
};

// Conjugate gradient for A x = b.
//
// A_dense is [n, n] and is used when row_ptr is null.  Otherwise the CSR
// triple (row_ptr, col_idx, values) describes A.
SolverResult solve_conjugate_gradient(const float* A_dense,
                                       const int* row_ptr,
                                       const int* col_idx,
                                       const float* values,
                                       const float* b,
                                       int n,
                                       int max_iter,
                                       float tol);

// Regularized least squares:
//
//     x = (A^T A + diag(lambda))^-1 A^T b
//
// A is [m, n].  This is the ridge-regression normal equation, solved with a
// Cholesky factorization of the (positive definite) normal matrix.
SolverResult solve_rls(const float* A, const float* b, const float* lambda, int m, int n);

}  // namespace cauveris
