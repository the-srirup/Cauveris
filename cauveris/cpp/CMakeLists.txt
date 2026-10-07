cmake_minimum_required(VERSION 3.18)
project(cauveris_kernels LANGUAGES CXX CUDA)

# Version
set(CAUVERIS_VERSION_MAJOR 1)
set(CAUVERIS_VERSION_MINOR 0)
set(CAUVERIS_VERSION_PATCH 0)

# C++ standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# CUDA standard
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

# Build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -Wpedantic -O3 -march=native")
    set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} -O3 -use_fast_math")
elseif(MSVC)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /W4 /O2 /arch:AVX2")
    set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} /O2 /use_fast_math")
endif()

# Find CUDA
find_package(CUDA REQUIRED)

# Find pybind11
find_package(pybind11 CONFIG REQUIRED)

# Include directories
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)
include_directories(${CUDA_INCLUDE_DIRS})

# Source files
set(KERNEL_SOURCES
    src/kernel_types.cpp
    src/local_kernels.cpp
    src/cross_kernels.cpp
    src/kernel_matrix.cpp
    src/convolution.cpp
    src/solver.cpp
)

set(CUDA_SOURCES
    cuda/local_kernels.cu
    cuda/cross_kernels.cu
    cuda/convolution.cu
    cuda/solver.cu
    cuda/matrix_ops.cu
)

# Main library
add_library(cauveris_kernels STATIC ${KERNEL_SOURCES} ${CUDA_SOURCES})
target_link_libraries(cauveris_kernels PUBLIC ${CUDA_LIBRARIES})
target_include_directories(cauveris_kernels PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

# Python bindings
pybind11_add_module(cauveris_kernels_py bindings/pybind11_module.cpp)
target_link_libraries(cauveris_kernels_py PRIVATE cauveris_kernels pybind11::module)

# Install targets
install(TARGETS cauveris_kernels
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
)

install(TARGETS cauveris_kernels_py
    LIBRARY DESTINATION ${PYTHON_INSTALL_DIR}
)

# Install headers
install(DIRECTORY include/ DESTINATION include)

# Python package setup
configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/bindings/pyproject.toml.in
    ${CMAKE_CURRENT_BINARY_DIR}/pyproject.toml
    @ONLY
)

# Tests
enable_testing()
add_subdirectory(tests)