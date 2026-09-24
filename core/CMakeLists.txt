cmake_minimum_required(VERSION 3.16)
project(fomoth_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

if(MSVC)
  add_compile_options(/W4)
else()
  add_compile_options(-Wall -Wextra -O2)
endif()

# the engine as a static library, shared by the CLI and the tests
add_library(fumble STATIC
  src/regret.cpp
  src/coach.cpp)
target_include_directories(fumble PUBLIC include)

# the CLI the Python layer shells out to (binary name: fumble)
add_executable(fumble_cli src/main.cpp)
target_link_libraries(fumble_cli PRIVATE fumble)
set_target_properties(fumble_cli PROPERTIES OUTPUT_NAME fumble)

enable_testing()

add_executable(test_regret tests/test_regret.cpp)
target_link_libraries(test_regret PRIVATE fumble)
add_test(NAME regret COMMAND test_regret)

add_executable(test_coach tests/test_coach.cpp)
target_link_libraries(test_coach PRIVATE fumble)
add_test(NAME coach COMMAND test_coach)
