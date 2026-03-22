cmake_minimum_required(VERSION 3.14)
project(stdiobus-cpp VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(STDIOBUS_CPP_EXCEPTIONS "Enable exception throwing mode" OFF)
option(STDIOBUS_BUILD_TESTS "Build tests" ON)
option(STDIOBUS_BUILD_EXAMPLES "Build examples" ON)

# Find libstdio_bus
if(DEFINED STDIO_BUS_LIB_DIR)
    set(STDIO_BUS_LIB_PATH "${STDIO_BUS_LIB_DIR}/libstdio_bus.a")
    set(STDIO_BUS_INCLUDE_DIR "${STDIO_BUS_LIB_DIR}/../include")
else()
    set(STDIO_BUS_LIB_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../../build/libstdio_bus.a")
    set(STDIO_BUS_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../include")
endif()

# Header-only library (thin wrapper + facade)
add_library(stdiobus-cpp INTERFACE)
target_include_directories(stdiobus-cpp INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${STDIO_BUS_INCLUDE_DIR}>
    $<INSTALL_INTERFACE:include>
)

if(STDIOBUS_CPP_EXCEPTIONS)
    target_compile_definitions(stdiobus-cpp INTERFACE STDIOBUS_CPP_EXCEPTIONS=1)
endif()

# Static library with implementation
add_library(stdiobus STATIC src/bus.cpp)
target_link_libraries(stdiobus PUBLIC stdiobus-cpp)
target_link_libraries(stdiobus PRIVATE ${STDIO_BUS_LIB_PATH})

if(STDIOBUS_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

if(STDIOBUS_BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

# Install
install(TARGETS stdiobus stdiobus-cpp
    EXPORT stdiobus-targets
    ARCHIVE DESTINATION lib
    INCLUDES DESTINATION include
)
install(DIRECTORY include/ DESTINATION include)
install(EXPORT stdiobus-targets
    FILE stdiobus-config.cmake
    NAMESPACE stdiobus::
    DESTINATION lib/cmake/stdiobus
)
