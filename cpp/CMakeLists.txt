cmake_minimum_required(VERSION 3.24)

# nvcc refuses to compile for a host compiler that is newer than the one it
# was tested against.  The flag has to be in place before project() runs,
# because the compiler identification compiles a probe program.  It is a
# warning about the pairing of the two tools, not about the code.
option(CAUVERIS_ALLOW_UNSUPPORTED_COMPILER
       "Pass -allow-unsupported-compiler to nvcc" ON)
if(CAUVERIS_ALLOW_UNSUPPORTED_COMPILER)
    set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} -allow-unsupported-compiler")
endif()

project(cauveris_kernels LANGUAGES CXX CUDA VERSION 0.2.0)

# ---------------------------------------------------------------------------
# Standards and build type
# ---------------------------------------------------------------------------

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)
set(CMAKE_CUDA_STANDARD_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# The CUDA runtime is linked statically into the extension.  A shared runtime
# would make the import fail on any machine that does not have the matching
# CUDA redistributable on its PATH, and the engine has to work wherever the
# Python package is installed.
set(CMAKE_CUDA_RUNTIME_LIBRARY Static)

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

find_package(CUDAToolkit REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

# nvcc refuses to compile for a host compiler that is newer than the one it
# was tested against.  It is a warning about the pairing, not about the code,
# so the check is allowed here and can be turned off for a matched toolchain.
option(CAUVERIS_ALLOW_UNSUPPORTED_COMPILER
       "Pass -allow-unsupported-compiler to nvcc" ON)

if(MSVC)
    add_compile_options(/W3 /O2 /DNDEBUG /D_CRT_SECURE_NO_WARNINGS)
else()
    add_compile_options(-Wall -Wextra -Wno-unused-parameter -O3 -DNDEBUG -fPIC)
endif()

# No -use_fast_math: the kernels reproduce the NumPy reference model, and
# fast math swaps the transcendentals for approximations.  The whole point of
# the GPU path is that it agrees with the CPU path.
add_compile_options($<$<COMPILE_LANGUAGE:CUDA>:--expt-relaxed-constexpr>)

# ---------------------------------------------------------------------------
# CUDA architectures
#
# "native" asks CMake to compile for the GPU in the build machine.  A build
# machine without a GPU (a CI runner, a Docker image) has no native
# architecture, so the list can be overridden from the outside.
# ---------------------------------------------------------------------------

if(NOT CMAKE_CUDA_ARCHITECTURES)
    set(CMAKE_CUDA_ARCHITECTURES "native" CACHE STRING "CUDA architectures to build for")
endif()

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

set(KERNEL_SOURCES
    cuda/propagation_kernels.cu
    cuda/device.cu
    cuda/linalg.cu
)

set(BINDING_SOURCES
    bindings/pybind11_module.cpp
)

add_library(cauveris_kernels_core STATIC ${KERNEL_SOURCES})

target_include_directories(cauveris_kernels_core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

target_link_libraries(cauveris_kernels_core PUBLIC CUDA::cudart)
target_compile_features(cauveris_kernels_core PRIVATE cxx_std_17)

pybind11_add_module(cauveris_kernels_py ${BINDING_SOURCES})

target_link_libraries(cauveris_kernels_py PRIVATE cauveris_kernels_core)
target_include_directories(cauveris_kernels_py PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)

set_target_properties(cauveris_kernels_py PROPERTIES PREFIX "")

# ---------------------------------------------------------------------------
# Installation
#
# scikit-build-core collects the files installed here into the wheel root.
# The extension is a top level module so that it does not fight with the
# "cauveris" Python package that ships in the same environment.
# ---------------------------------------------------------------------------

install(TARGETS cauveris_kernels_py
    LIBRARY DESTINATION .
    RUNTIME DESTINATION .
)

install(DIRECTORY include/
    DESTINATION include/cauveris
    FILES_MATCHING PATTERN "*.h"
)

install(TARGETS cauveris_kernels_core
    ARCHIVE DESTINATION lib
)

message(STATUS "=== Cauveris Kernels Build Configuration ===")
message(STATUS "  Project version: ${PROJECT_VERSION}")
message(STATUS "  CUDA toolkit: ${CUDAToolkit_VERSION}")
message(STATUS "  CUDA architectures: ${CMAKE_CUDA_ARCHITECTURES}")
message(STATUS "  Python: ${Python3_VERSION}")
message(STATUS "  pybind11: ${pybind11_VERSION}")
message(STATUS "  Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "=============================================")
