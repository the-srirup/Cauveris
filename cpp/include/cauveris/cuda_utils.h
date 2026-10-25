/**
 * Small helpers shared by the CUDA translation units.
 */

#pragma once

#include <cuda_runtime.h>

#include <stdexcept>
#include <string>

namespace cauveris {

// Every CUDA call that can fail is checked.  A CUDA error is sticky: the
// first failure poisons the context, and ignoring it turns a clear error
// message into a crash somewhere else entirely.
#define CAUVERIS_CUDA_CHECK(call)                                                  \
    do {                                                                           \
        cudaError_t _err = (call);                                                 \
        if (_err != cudaSuccess) {                                                 \
            throw std::runtime_error(std::string("CUDA error in ") + #call +      \
                                     ": " + cudaGetErrorString(_err));             \
        }                                                                          \
    } while (0)

#define CAUVERIS_CUDA_CHECK_KERNEL() CAUVERIS_CUDA_CHECK(cudaGetLastError())

}  // namespace cauveris
