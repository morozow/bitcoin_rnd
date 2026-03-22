/**
 * @file test_types.cpp
 * @brief Tests for type definitions
 */

#include <gtest/gtest.h>
#include <stdiobus/types.hpp>

using namespace stdiobus;

TEST(State, Values) {
    EXPECT_EQ(static_cast<int>(State::Created), 0);
    EXPECT_EQ(static_cast<int>(State::Starting), 1);
    EXPECT_EQ(static_cast<int>(State::Running), 2);
    EXPECT_EQ(static_cast<int>(State::Stopping), 3);
    EXPECT_EQ(static_cast<int>(State::Stopped), 4);
}

TEST(State, Names) {
    EXPECT_EQ(state_name(State::Created), "Created");
    EXPECT_EQ(state_name(State::Starting), "Starting");
    EXPECT_EQ(state_name(State::Running), "Running");
    EXPECT_EQ(state_name(State::Stopping), "Stopping");
    EXPECT_EQ(state_name(State::Stopped), "Stopped");
}

TEST(ListenMode, Values) {
    EXPECT_EQ(static_cast<int>(ListenMode::None), 0);
    EXPECT_EQ(static_cast<int>(ListenMode::Tcp), 1);
    EXPECT_EQ(static_cast<int>(ListenMode::Unix), 2);
}

TEST(Stats, DefaultValues) {
    Stats stats;
    EXPECT_EQ(stats.messages_in, 0u);
    EXPECT_EQ(stats.messages_out, 0u);
    EXPECT_EQ(stats.bytes_in, 0u);
    EXPECT_EQ(stats.bytes_out, 0u);
    EXPECT_EQ(stats.worker_restarts, 0u);
    EXPECT_EQ(stats.routing_errors, 0u);
    EXPECT_EQ(stats.client_connects, 0u);
    EXPECT_EQ(stats.client_disconnects, 0u);
}

TEST(ListenerConfig, Default) {
    ListenerConfig config;
    EXPECT_EQ(config.mode, ListenMode::None);
    EXPECT_TRUE(config.tcp_host.empty());
    EXPECT_EQ(config.tcp_port, 0);
    EXPECT_TRUE(config.unix_path.empty());
}

TEST(ListenerConfig, TcpConfig) {
    ListenerConfig config;
    config.mode = ListenMode::Tcp;
    config.tcp_host = "127.0.0.1";
    config.tcp_port = 8080;
    
    EXPECT_EQ(config.mode, ListenMode::Tcp);
    EXPECT_EQ(config.tcp_host, "127.0.0.1");
    EXPECT_EQ(config.tcp_port, 8080);
}

TEST(ListenerConfig, UnixConfig) {
    ListenerConfig config;
    config.mode = ListenMode::Unix;
    config.unix_path = "/tmp/bus.sock";
    
    EXPECT_EQ(config.mode, ListenMode::Unix);
    EXPECT_EQ(config.unix_path, "/tmp/bus.sock");
}

TEST(Options, Default) {
    Options opts;
    EXPECT_TRUE(opts.config_path.empty());
    EXPECT_TRUE(opts.config_json.empty());
    EXPECT_EQ(opts.listener.mode, ListenMode::None);
    EXPECT_EQ(opts.log_level, 1);
    EXPECT_FALSE(opts.on_message);
    EXPECT_FALSE(opts.on_error);
}

TEST(Duration, ToMs) {
    using namespace std::chrono;
    
    EXPECT_EQ(to_ms(milliseconds(100)), 100);
    EXPECT_EQ(to_ms(seconds(1)), 1000);
    EXPECT_EQ(to_ms(minutes(1)), 60000);
    EXPECT_EQ(to_ms(milliseconds(0)), 0);
}

TEST(Callbacks, MessageCallback) {
    std::string received;
    MessageCallback cb = [&received](std::string_view msg) {
        received = std::string(msg);
    };
    
    cb("test message");
    EXPECT_EQ(received, "test message");
}

TEST(Callbacks, ErrorCallback) {
    ErrorCode received_code = ErrorCode::Ok;
    std::string received_msg;
    
    ErrorCallback cb = [&](ErrorCode code, std::string_view msg) {
        received_code = code;
        received_msg = std::string(msg);
    };
    
    cb(ErrorCode::Timeout, "Request timed out");
    EXPECT_EQ(received_code, ErrorCode::Timeout);
    EXPECT_EQ(received_msg, "Request timed out");
}

TEST(Callbacks, LogCallback) {
    int received_level = -1;
    std::string received_msg;
    
    LogCallback cb = [&](int level, std::string_view msg) {
        received_level = level;
        received_msg = std::string(msg);
    };
    
    cb(2, "Warning message");
    EXPECT_EQ(received_level, 2);
    EXPECT_EQ(received_msg, "Warning message");
}

TEST(Callbacks, WorkerCallback) {
    int received_id = -1;
    std::string received_event;
    
    WorkerCallback cb = [&](int worker_id, std::string_view event) {
        received_id = worker_id;
        received_event = std::string(event);
    };
    
    cb(3, "started");
    EXPECT_EQ(received_id, 3);
    EXPECT_EQ(received_event, "started");
}
