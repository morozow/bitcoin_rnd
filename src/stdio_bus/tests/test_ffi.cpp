/**
 * @file test_ffi.cpp
 * @brief Tests for FFI thin wrapper
 */

#include <gtest/gtest.h>
#include <stdiobus/ffi.hpp>

using namespace stdiobus;
using namespace stdiobus::ffi;

TEST(FFI, HandleDefault) {
    Handle h;
    EXPECT_FALSE(h);
    EXPECT_EQ(h.get(), nullptr);
}

TEST(FFI, HandleFromPointer) {
    // Can't test with real pointer without C library
    // Just test null handling
    Handle h(nullptr);
    EXPECT_FALSE(h);
}

TEST(FFI, ToState) {
    EXPECT_EQ(to_state(STDIO_BUS_STATE_CREATED), State::Created);
    EXPECT_EQ(to_state(STDIO_BUS_STATE_STARTING), State::Starting);
    EXPECT_EQ(to_state(STDIO_BUS_STATE_RUNNING), State::Running);
    EXPECT_EQ(to_state(STDIO_BUS_STATE_STOPPING), State::Stopping);
    EXPECT_EQ(to_state(STDIO_BUS_STATE_STOPPED), State::Stopped);
}

TEST(FFI, ToStats) {
    stdio_bus_stats_t c_stats{};
    c_stats.messages_in = 100;
    c_stats.messages_out = 50;
    c_stats.bytes_in = 10000;
    c_stats.bytes_out = 5000;
    c_stats.worker_restarts = 2;
    c_stats.routing_errors = 1;
    c_stats.client_connects = 10;
    c_stats.client_disconnects = 5;
    
    Stats stats = to_stats(c_stats);
    
    EXPECT_EQ(stats.messages_in, 100u);
    EXPECT_EQ(stats.messages_out, 50u);
    EXPECT_EQ(stats.bytes_in, 10000u);
    EXPECT_EQ(stats.bytes_out, 5000u);
    EXPECT_EQ(stats.worker_restarts, 2u);
    EXPECT_EQ(stats.routing_errors, 1u);
    EXPECT_EQ(stats.client_connects, 10u);
    EXPECT_EQ(stats.client_disconnects, 5u);
}

TEST(FFI, CApiVersion) {
    EXPECT_EQ(STDIO_BUS_EMBED_API_VERSION, 2);
}

TEST(FFI, ErrorCodes) {
    EXPECT_EQ(STDIO_BUS_ERR_CONFIG, -10);
    EXPECT_EQ(STDIO_BUS_ERR_WORKER, -11);
    EXPECT_EQ(STDIO_BUS_ERR_ROUTING, -12);
    EXPECT_EQ(STDIO_BUS_ERR_BUFFER, -13);
    EXPECT_EQ(STDIO_BUS_ERR_INVALID, -14);
    EXPECT_EQ(STDIO_BUS_ERR_STATE, -15);
}

TEST(FFI, ListenModeValues) {
    EXPECT_EQ(STDIO_BUS_LISTEN_NONE, 0);
    EXPECT_EQ(STDIO_BUS_LISTEN_TCP, 1);
    EXPECT_EQ(STDIO_BUS_LISTEN_UNIX, 2);
}

TEST(FFI, StateValues) {
    EXPECT_EQ(STDIO_BUS_STATE_CREATED, 0);
    EXPECT_EQ(STDIO_BUS_STATE_STARTING, 1);
    EXPECT_EQ(STDIO_BUS_STATE_RUNNING, 2);
    EXPECT_EQ(STDIO_BUS_STATE_STOPPING, 3);
    EXPECT_EQ(STDIO_BUS_STATE_STOPPED, 4);
}
