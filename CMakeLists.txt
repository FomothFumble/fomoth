cmake_minimum_required(VERSION 3.16)
project(fomoth LANGUAGES CXX)

# The C++ core lives in core/. Build it with:
#     cmake -S . -B build && cmake --build build && ctest --test-dir build
add_subdirectory(core)
