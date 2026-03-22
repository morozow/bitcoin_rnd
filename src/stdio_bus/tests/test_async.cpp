/**
 * @file test_async.cpp
 * @brief Tests for async adaptor
 */

#include <gtest/gtest.h>
#include <stdiobus/async.hpp>

using namespace stdiobus;

TEST(AsyncResult, DefaultConstruction) {
    AsyncResult result;
    EXPECT_FALSE(result.error);
    EXPECT_TRUE(result.response.empty());
    EXPECT_TRUE(result);  // No error = success
}

TEST(AsyncResult, WithError) {
    AsyncResult result{Error(ErrorCode::Timeout), ""};
    EXPECT_TRUE(result.error);
    EXPECT_FALSE(result);  // Has error = failure
}

TEST(AsyncResult, WithResponse) {
    AsyncResult result{Error::ok(), R"({"result":"ok"})"};
    EXPECT_FALSE(result.error);
    EXPECT_TRUE(result);
    EXPECT_EQ(result.response, R"({"result":"ok"})");
}

TEST(AsyncBus, Construction) {
    // Will fail without valid config, but tests API
    AsyncBus bus("nonexistent.json");
    EXPECT_FALSE(bus.bus());
}

TEST(AsyncBus, ConstructFromOptions) {
    Options opts;
    opts.config_path = "nonexistent.json";
    
    AsyncBus bus(std::move(opts));
    EXPECT_FALSE(bus.bus());
}

TEST(AsyncBus, StartInvalid) {
    AsyncBus bus("nonexistent.json");
    auto err = bus.start();
    EXPECT_TRUE(err);
}

TEST(AsyncBus, StopInvalid) {
    AsyncBus bus("nonexistent.json");
    auto err = bus.stop();
    EXPECT_TRUE(err);
}

TEST(AsyncBus, PumpInvalid) {
    AsyncBus bus("nonexistent.json");
    // Should not crash
    int result = bus.pump(std::chrono::milliseconds(0));
    EXPECT_LT(result, 0);  // Error
}

TEST(AsyncBus, NotifyInvalid) {
    AsyncBus bus("nonexistent.json");
    auto err = bus.notify(R"({"jsonrpc":"2.0","method":"test"})");
    EXPECT_TRUE(err);
}

TEST(AsyncBus, RequestAsyncInvalid) {
    AsyncBus bus("nonexistent.json");
    
    auto future = bus.request_async(R"({"jsonrpc":"2.0","method":"test","id":1})");
    
    // Future should be ready immediately with error
    auto status = future.wait_for(std::chrono::milliseconds(100));
    EXPECT_EQ(status, std::future_status::ready);
    
    auto result = future.get();
    EXPECT_TRUE(result.error);
}

TEST(AsyncBus, CheckTimeouts) {
    AsyncBus bus("nonexistent.json");
    // Should not crash
    bus.check_timeouts();
}

TEST(AsyncBus, BusAccess) {
    AsyncBus async_bus("nonexistent.json");
    
    Bus& bus = async_bus.bus();
    const Bus& const_bus = async_bus.bus();
    
    EXPECT_FALSE(bus);
    EXPECT_FALSE(const_bus);
}

// Integration test (requires valid config and libstdio_bus)
// Uncomment when running with real library
/*
TEST(AsyncBus, Integration) {
    AsyncBus bus("examples/config.json");
    
    ASSERT_FALSE(bus.start());
    
    auto future = bus.request_async(
        R"({"jsonrpc":"2.0","method":"echo","params":{"msg":"hello"},"id":1})",
        std::chrono::seconds(5)
    );
    
    // Pump until ready
    while (future.wait_for(std::chrono::milliseconds(0)) != std::future_status::ready) {
        bus.pump(std::chrono::milliseconds(10));
        bus.check_timeouts();
    }
    
    auto result = future.get();
    EXPECT_TRUE(result);
    EXPECT_FALSE(result.response.empty());
    
    bus.stop();
}
*/
