/**
 * Propagation kernels - the CUDA evaluation of the holographic Green's
 * functions.
 *
 * The characteristic time of every (component, boundary layer) pair is
 * supplied by the caller.  That is deliberate: the *policy* of the model
 * (how fast a database publishes its metrics compared with a queue) lives in
 * one place - the Python reference implementation - and this library only
 * evaluates and convolves.  A second copy of those rules written in CUDA
 * would be a second place for them to drift.
 *
 * All functions take and return HOST pointers; the transfers are handled
 * internally.  A caller cannot accidentally hand a host array to a kernel.
 */

#pragma once

#include <cstdint>

#include "cauveris/kernel_types.h"

namespace cauveris {

// Configuration of the sampled time axis and of the decay model.
struct PropagationConfig {
    double time_step_ns = 1e6;    // sample spacing [ns]
    int    num_steps    = 10000;  // number of samples
    double max_time_ns  = 1e10;   // end of the window [ns]

    DecayType       decay_type    = DecayType::EXPONENTIAL;
    NormalizationType normalization = NormalizationType::L1_NORM;

    // Gamma decay: shape k, the scale is tau / k.
    double gamma_shape = 2.0;
    // Bi-exponential decay: weight of the fast component, and its time
    // constant as a fraction of the slow one.
    double biexp_alpha      = 0.7;
    double biexp_fast_ratio = 0.1;
};

// Evaluate the local propagation kernel of every (component, layer) pair.
//
//   tau_ns        [num_pairs]  characteristic time [ns]
//   kernel_values [num_pairs * num_steps]  output
//   integral      [num_pairs]  integral of the kernel
//   peak_time_ns  [num_pairs]  time of the maximum
//   half_life_ns  [num_pairs]  time to fall to half the peak
//
// The pairs are flat: a component with three boundary layers contributes
// three pairs.  A rectangular [component][layer] grid would force every
// component to have the same number of layers, which real topologies do not
// have.  The kernel of pair p occupies kernel_values[p * num_steps ...].
void build_local_kernels(const double* tau_ns,
                         int num_pairs,
                         const PropagationConfig& config,
                         int device_id,
                         float* kernel_values,
                         double* integral,
                         double* peak_time_ns,
                         double* half_life_ns);

// Cross propagation: the response at the target boundary to a change at the
// source boundary.
//
//     cross(t) = conv(shift(source, shift), target)(t)
//
// where the shift is the transport delay (network latency plus queueing)
// expressed in samples, and the convolution is truncated to the length of
// the time axis.
//
//   src_kernel   [num_pairs * num_steps]
//   dst_kernel   [num_pairs * num_steps]
//   shift_steps  [num_pairs]
//   cross_values [num_pairs * num_steps]  output
void build_cross_kernels(const float* src_kernel,
                         const float* dst_kernel,
                         const int* shift_steps,
                         int num_pairs,
                         const PropagationConfig& config,
                         int device_id,
                         float* cross_values);

// Assemble the measurement kernel matrix.
//
//   values     [num_pairs * num_steps]  the kernel of every pair
//   row_index  [num_pairs]  the observable state the pair writes into
//   col_index  [num_pairs]  the source state the pair reads from
//   matrix     [n_rows * n_cols * n_time]  output
//
// Every pair contributes the first min(num_steps, n_time) samples of its
// kernel to matrix[row_index[p], col_index[p], :].  Writing the pairs
// directly into the matrix avoids materialising the pair list as a dense
// tensor first.
void assemble_kernel_matrix(const float* values,
                             const int* row_index,
                             const int* col_index,
                             int num_pairs,
                             int num_steps,
                             int n_time,
                             int n_rows,
                             int n_cols,
                             float* matrix);

}  // namespace cauveris
