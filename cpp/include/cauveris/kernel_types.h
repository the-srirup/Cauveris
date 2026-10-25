/**
 * Core types for the holographic causal kernel engine.
 *
 * The engine computes Green's functions that describe how an internal state
 * change propagates to the observable boundary of a system (its logs, its
 * metrics, its traces).  These types describe the two physical choices that
 * fully determine such a function: how the influence decays with time, and
 * how the sampled function is scaled.
 */

#pragma once

#include <cstdint>

namespace cauveris {

// How the influence of an internal state change decays with time.
//
//   EXPONENTIAL     exp(-t/tau) / tau
//   GAMMA           Gamma PDF, shape k, scale tau/k
//   BI_EXPONENTIAL  0.7 * exp(-t/(0.1 tau)) / (0.1 tau)
//                    + 0.3 * exp(-t/tau) / tau
//
// The first and third are the "buffer flush plus scrape" picture: a fast
// component and a slow one.  The second is the queueing picture.
enum class DecayType : uint8_t {
    EXPONENTIAL    = 0,
    GAMMA          = 1,
    BI_EXPONENTIAL = 2,
};

// How the sampled kernel is scaled.
//
// The integral is always taken with the trapezoid rule over the sampled time
// axis - the same rule the reference NumPy implementation uses - so that the
// GPU and CPU paths agree to floating point precision.
enum class NormalizationType : uint8_t {
    NONE    = 0,   // leave the raw density alone
    L1_NORM = 1,   // divide by the integral (conservation of influence)
    L2_NORM = 2,   // divide by the L2 norm of the density
    MAX_NORM = 3,  // divide by the peak value
};

}  // namespace cauveris
