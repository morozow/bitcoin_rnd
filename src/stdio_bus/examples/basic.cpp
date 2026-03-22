/**
 * @file basic.cpp
 * @brief Basic usage example for stdiobus C++ SDK
 */

#include <stdiobus.hpp>
#include <iostream>
#include <chrono>

int main(int argc, char* argv[]) {
    const char* config_path = argc > 1 ? argv[1] : "config.json";
    
    // Create bus from config file
    stdiobus::Bus bus(config_path);
    
    if (!bus) {
        std::cerr << "Failed to create bus from " << config_path << std::endl;
        return 1;
    }
    
    // Set message callback
    bus.on_message([](std::string_view msg) {
        std::cout << "Received: " << msg << std::endl;
    });
    
    // Set error callback
    bus.on_error([](stdiobus::ErrorCode code, std::string_view msg) {
        std::cerr << "Error [" << static_cast<int>(code) << "]: " << msg << std::endl;
    });
    
    // Set worker event callback
    bus.on_worker([](int worker_id, std::string_view event) {
        std::cout << "Worker " << worker_id << ": " << event << std::endl;
    });
    
    // Start the bus
    if (auto err = bus.start(); err) {
        std::cerr << "Failed to start: " << err.message() << std::endl;
        return 1;
    }
    
    std::cout << "Bus started with " << bus.worker_count() << " workers" << std::endl;
    
    // Send a test request
    const char* request = R"({"jsonrpc":"2.0","method":"echo","params":{"message":"hello"},"id":1})";
    if (auto err = bus.send(request); err) {
        std::cerr << "Failed to send: " << err.message() << std::endl;
    }
    
    // Event loop - process for 5 seconds
    auto start = std::chrono::steady_clock::now();
    while (bus.is_running()) {
        bus.step(std::chrono::milliseconds(100));
        
        auto elapsed = std::chrono::steady_clock::now() - start;
        if (elapsed > std::chrono::seconds(5)) {
            break;
        }
    }
    
    // Print stats
    auto stats = bus.stats();
    std::cout << "\nStats:" << std::endl;
    std::cout << "  Messages in:  " << stats.messages_in << std::endl;
    std::cout << "  Messages out: " << stats.messages_out << std::endl;
    std::cout << "  Bytes in:     " << stats.bytes_in << std::endl;
    std::cout << "  Bytes out:    " << stats.bytes_out << std::endl;
    
    // Stop gracefully
    if (auto err = bus.stop(std::chrono::seconds(5)); err) {
        std::cerr << "Failed to stop: " << err.message() << std::endl;
    }
    
    std::cout << "Bus stopped" << std::endl;
    return 0;
}
