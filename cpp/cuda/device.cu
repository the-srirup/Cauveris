/**
 * Device queries.  The information comes from the CUDA runtime itself, so
 * it describes the device that is actually present rather than a guess
 * based on the driver version.
 */

#include "cauveris/device.h"

#include <cuda_runtime.h>

#include <cstdio>

namespace cauveris {

bool query_device_info(int device_id, DeviceInfo* out) {
    if (out == nullptr) {
        return false;
    }

    int count = 0;
    if (cudaGetDeviceCount(&count) != cudaSuccess || count <= 0) {
        cudaGetLastError();  // clear the sticky-free error
        return false;
    }
    if (device_id < 0 || device_id >= count) {
        return false;
    }

    cudaDeviceProp prop;
    if (cudaGetDeviceProperties(&prop, device_id) != cudaSuccess) {
        cudaGetLastError();
        return false;
    }

    out->device_id              = device_id;
    out->name                  = std::string(prop.name);
    out->compute_major         = prop.major;
    out->compute_minor         = prop.minor;
    out->multi_processor_count = prop.multiProcessorCount;
    out->total_memory_bytes    = static_cast<size_t>(prop.totalGlobalMem);
    out->clock_rate_khz        = prop.clockRate;
    out->memory_clock_khz      = prop.memoryClockRate;
    out->memory_bus_width      = prop.memoryBusWidth;
    out->l2_cache_size         = prop.l2CacheSize;
    out->max_threads_per_block = prop.maxThreadsPerBlock;
    out->warp_size             = prop.warpSize;

    int runtime_version = 0;
    if (cudaRuntimeGetVersion(&runtime_version) == cudaSuccess) {
        out->cuda_runtime_version = std::to_string(runtime_version / 1000) + "." +
                                    std::to_string((runtime_version % 1000) / 10);
    }
    int driver_version = 0;
    if (cudaDriverGetVersion(&driver_version) == cudaSuccess) {
        out->driver_version = std::to_string(driver_version / 1000) + "." +
                              std::to_string((driver_version % 1000) / 10);
    }

    return true;
}

}  // namespace cauveris
