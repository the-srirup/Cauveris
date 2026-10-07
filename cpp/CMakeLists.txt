cmake_minimum_required(VERSION 3.18)
project(cauveris_kernels LANGUAGES CXX CUDA VERSION 0.1.0)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# CUDA standard
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

# Build configuration
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# CUDA architectures - use native for development, can be overridden
if(NOT CMAKE_CUDA_ARCHITECTURES)
    set(CMAKE_CUDA_ARCHITECTURES "80;86;89;90" CACHE STRING "CUDA architectures to build for")
endif()

# Output directories
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

# ============================================================================
# Find Dependencies
# ============================================================================

# CUDA
find_package(CUDA REQUIRED)

# Python
find_package(Python3 COMPONENTS Development REQUIRED)

# pybind11 - use config mode
find_package(pybind11 CONFIG REQUIRED)

# ============================================================================
# Include Directories
# ============================================================================

include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${Python3_INCLUDE_DIRS}
    ${pybind11_INCLUDE_DIRS}
)

# ============================================================================
# Compile Options
# ============================================================================

# Common compile options
if(MSVC)
    add_compile_options(
        /W3
        /O2
        /DNDEBUG
        /D_CRT_SECURE_NO_WARNINGS
    )
else()
    add_compile_options(
        -Wall
        -Wextra
        -Wno-unused-parameter
        -O3
        -DNDEBUG
        -fPIC
    )
endif()

# CUDA compile options
set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} -Xcompiler=${CMAKE_CXX_FLAGS}")
set(CMAKE_CUDA_FLAGS_DEBUG "${CMAKE_CUDA_FLAGS_DEBUG} -G -lineinfo")
set(CMAKE_CUDA_FLAGS_RELEASE "${CMAKE_CUDA_FLAGS_RELEASE} -O3 -use_fast_math")

# Enable FP16 tensor cores for Volta+
add_compile_options(
    $<$<COMPILE_LANGUAGE:CUDA>:-D__CUDA_NO_HALF2_OPERATORS__=0>
    $<$<COMPILE_LANGUAGE:CUDA>:-D__CUDA_NO_HALF_CONVERSIONS__=0>
)

# ============================================================================
# Source Files
# ============================================================================

set(KERNEL_SOURCES
    cuda/local_kernels.cu
    cuda/convolution.cu
    cuda/solver.cu
    cuda/matrix_ops.cu
)

set(BINDING_SOURCES
    bindings/pybind11_module.cpp
)

# ============================================================================
# Core Library Target
# ============================================================================

add_library(cauveris_kernels_core STATIC ${KERNEL_SOURCES})

target_include_directories(cauveris_kernels_core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

target_link_libraries(cauveris_kernels_core PUBLIC
    ${CUDA_LIBRARIES}
    nvrtc  # For JIT compilation support
)

# Compile with C++17
target_compile_features(cauveris_kernels_core PRIVATE cxx_std_17)

# ============================================================================
# Python Module Target
# ============================================================================

pybind11_add_module(cauveris_kernels_py ${BINDING_SOURCES})

target_link_libraries(cauveris_kernels_py PRIVATE
    cauveris_kernels_core
    ${Python3_LIBRARIES}
    ${CUDA_LIBRARIES}
)

target_include_directories(cauveris_kernels_py PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Set output name without platform-specific suffix
set_target_properties(cauveris_kernels_py PROPERTIES
    PREFIX ""
    SUFFIX "${PYTHON_MODULE_EXTENSION}"
)

# ============================================================================
# Installation
# ============================================================================

install(TARGETS cauveris_kernels_core
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
)

install(TARGETS cauveris_kernels_py
    LIBRARY DESTINATION ${Python3_SITEARCH}/cauveris
    RUNTIME DESTINATION ${Python3_SITEARCH}/cauveris
)

install(DIRECTORY include/
    DESTINATION include/cauveris
    FILES_MATCHING PATTERN "*.h"
)

# ============================================================================
# Package Config
# ============================================================================

include(CMakePackageConfigHelpers)
write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/cauverisConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

# Export targets for downstream use
export(EXPORT cauveris-targets
    FILE ${CMAKE_CURRENT_BINARY_DIR}/cauverisTargets.cmake
)

# ============================================================================
# Print Configuration Summary
# ============================================================================

message(STATUS "=== Cauveris Kernels Build Configuration ===")
message(STATUS "  Project version: ${PROJECT_VERSION}")
message(STATUS "  CUDA version: ${CUDA_VERSION}")
message(STATUS "  CUDA architectures: ${CMAKE_CUDA_ARCHITECTURES}")
message(STATUS "  Python version: ${Python3_VERSION}")
message(STATUS "  Python include: ${Python3_INCLUDE_DIRS}")
message(STATUS "  pybind11 version: ${pybind11_VERSION}")
message(STATUS "  Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "=============================================")