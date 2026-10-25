/**
 * Information about the CUDA device the engine runs on.
 */

#pragma once

#include <cstdint>
#include <string>

namespace cauveris {

struct DeviceInfo {
    int    device_id          = -1;
    std::string name          = "unknown";
    int    compute_major      = 0;
    int    compute_minor      = 0;
    int    multi_processor_count = 0;
    size_t total_memory_bytes = 0;
    int    clock_rate_khz     = 0;
    int    memory_clock_khz   = 0;
    int    memory_bus_width   = 0;
    int    l2_cache_size      = 0;
    int    max_threads_per_block = 0;
    int    warp_size          = 0;
    std::string cuda_runtime_version = "unknown";
    std::string driver_version        = "unknown";
};

// Query the device.  Returns false when there is no usable device, which is
// a normal answer (the engine then runs on the CPU) and not an error.
bool query_device_info(int device_id, DeviceInfo* out);

}  // namespace cauveris
