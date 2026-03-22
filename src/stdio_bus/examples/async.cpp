/**
 * @file async.cpp
 * @brief Async usage example with std::future
 */

#include <stdiobus.hpp>
#include <stdiobus/async.hpp>
#include <iostream>
#include <vector>

int main(int argc, char* argv[]) {
    const char* config_path = argc > 1 ? argv[1] : "config.json";
    
    // Create async bus
    stdiobus::AsyncBus bus(config_path);
    
    if (!bus.bus()) {
        std::cerr << "Failed to create bus" << std::endl;
        return 1;
    }
    
    // Start
    if (auto err = bus.start(); err) {
        std::cerr << "Failed to start: " << err.message() << std::endl;
        return 1;
    }
    
    std::cout << "Sending 5 async requests..." << std::endl;
    
    // Send multiple async requests
    std::vector<std::future<stdiobus::AsyncResult>> futures;
    
    for (int i = 1; i <= 5; i++) {
        std::string request = R"({"jsonrpc":"2.0","method":"echo","params":{"n":)" 
                            + std::to_string(i) + R"(},"id":)" + std::to_string(i) + "}";
        
        futures.push_back(bus.request_async(request, std::chrono::seconds(10)));
    }
    
    // Pump until all futures are ready
    int completed = 0;
    while (completed < 5) {
        bus.pump(std::chrono::milliseconds(10));
        bus.check_timeouts();
        
        completed = 0;
        for (auto& f : futures) {
            if (f.wait_for(std::chrono::milliseconds(0)) == std::future_status::ready) {
                completed++;
            }
        }
    }
    
    // Get results
    std::cout << "\nResults:" << std::endl;
    for (size_t i = 0; i < futures.size(); i++) {
        auto result = futures[i].get();
        if (result) {
            std::cout << "  Request " << (i + 1) << ": " << result.response << std::endl;
        } else {
            std::cout << "  Request " << (i + 1) << " failed: " << result.error.message() << std::endl;
        }
    }
    
    // Stop
    bus.stop();
    std::cout << "\nDone" << std::endl;
    
    return 0;
}
