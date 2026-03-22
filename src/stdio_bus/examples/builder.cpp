/**
 * @file builder.cpp
 * @brief Builder pattern example
 */

#include <stdiobus.hpp>
#include <iostream>

int main(int argc, char* argv[]) {
    const char* config_path = argc > 1 ? argv[1] : "config.json";
    
    // Build bus with fluent API
    auto bus = stdiobus::BusBuilder()
        .config_path(config_path)
        .log_level(1)  // INFO
        .on_message([](std::string_view msg) {
            std::cout << "[MSG] " << msg << std::endl;
        })
        .on_error([](stdiobus::ErrorCode code, std::string_view msg) {
            std::cerr << "[ERR] " << stdiobus::error_code_name(code) << ": " << msg << std::endl;
        })
        .on_log([](int level, std::string_view msg) {
            const char* levels[] = {"DEBUG", "INFO", "WARN", "ERROR"};
            std::cout << "[" << levels[level] << "] " << msg << std::endl;
        })
        .on_worker([](int id, std::string_view event) {
            std::cout << "[WORKER " << id << "] " << event << std::endl;
        })
        .build();
    
    if (!bus) {
        std::cerr << "Failed to create bus" << std::endl;
        return 1;
    }
    
    // Start and run
    if (auto err = bus.start(); err) {
        std::cerr << "Start failed: " << err.message() << std::endl;
        return 1;
    }
    
    // Send request
    bus.send(R"({"jsonrpc":"2.0","method":"ping","id":1})");
    
    // Run for 2 seconds
    for (int i = 0; i < 20; i++) {
        bus.step(std::chrono::milliseconds(100));
    }
    
    // Stop
    bus.stop();
    
    return 0;
}
