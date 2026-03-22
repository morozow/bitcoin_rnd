include(FetchContent)

# Fetch GoogleTest
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
)
FetchContent_MakeAvailable(googletest)

# Test executable
add_executable(stdiobus_tests
    test_error.cpp
    test_types.cpp
    test_ffi.cpp
    test_bus.cpp
    test_async.cpp
)

target_link_libraries(stdiobus_tests PRIVATE
    stdiobus
    GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(stdiobus_tests)
