/**
 * @file runner.cpp
 * @brief Persistent stdio_bus runner - keeps the bus running until Ctrl+C
 * 
 * Usage: 
 *   ./runner --config <path.json>                    # stdio mode (embedded)
 *   ./runner --config <path.json> --tcp 8080         # TCP mode on port 8080
 *   ./runner --config <path.json> --unix /tmp/bus.sock  # Unix socket mode
 */

#include <stdiobus.hpp>
#include <iostream>
#include <csignal>
#include <atomic>
#include <cstring>

static std::atomic<bool> g_running{true};

void signal_handler(int sig) {
    (void)sig;
    std::cout << "\nShutdown requested..." << std::endl;
    g_running = false;
}

void print_usage(const char* prog) {
    std::cerr << "Usage: " << prog << " --config <path.json> [--tcp <port>] [--unix <path>]" << std::endl;
    std::cerr << std::endl;
    std::cerr << "Options:" << std::endl;
    std::cerr << "  --config <path>   Path to JSON config file (required)" << std::endl;
    std::cerr << "  --tcp <port>      Listen on TCP port (e.g., 8080)" << std::endl;
    std::cerr << "  --unix <path>     Listen on Unix socket (e.g., /tmp/bus.sock)" << std::endl;
    std::cerr << std::endl;
    std::cerr << "Without --tcp or --unix, runs in embedded stdio mode." << std::endl;
}

int main(int argc, char* argv[]) {
    // Parse arguments
    const char* config_path = nullptr;
    uint16_t tcp_port = 0;
    const char* unix_path = nullptr;
    
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--config") == 0 && i + 1 < argc) {
            config_path = argv[++i];
        } else if (strcmp(argv[i], "--tcp") == 0 && i + 1 < argc) {
            tcp_port = static_cast<uint16_t>(std::atoi(argv[++i]));
        } else if (strcmp(argv[i], "--unix") == 0 && i + 1 < argc) {
            unix_path = argv[++i];
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            return 0;
        }
    }
    
    if (!config_path) {
        print_usage(argv[0]);
        return 1;
    }
    
    std::cout << "Creating stdio_bus with config: " << config_path << std::endl;
    
    // Build bus with options
    auto builder = stdiobus::BusBuilder()
        .config_path(config_path)
        .on_message([](std::string_view msg) {
            std::cout << "[MSG] " << msg << std::endl;
        })
        .on_error([](stdiobus::ErrorCode code, std::string_view msg) {
            std::cerr << "[ERR " << static_cast<int>(code) << "] " << msg << std::endl;
        })
        .on_worker([](int worker_id, std::string_view event) {
            std::cout << "[WORKER " << worker_id << "] " << event << std::endl;
        });
    
    // Configure listener mode
    if (tcp_port > 0) {
        std::cout << "Listening on TCP port " << tcp_port << std::endl;
        builder.listen_tcp("0.0.0.0", tcp_port);
    } else if (unix_path) {
        std::cout << "Listening on Unix socket: " << unix_path << std::endl;
        builder.listen_unix(unix_path);
    } else {
        std::cout << "Running in embedded stdio mode" << std::endl;
    }
    
    auto bus = builder.build();
    
    if (!bus) {
        std::cerr << "Failed to create bus" << std::endl;
        return 1;
    }
    
    // Setup signal handlers
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // Start
    if (auto err = bus.start(); err) {
        std::cerr << "Failed to start: " << err.message() << std::endl;
        return 1;
    }
    
    std::cout << "stdio_bus RUNNING with " << bus.worker_count() << " workers" << std::endl;
    std::cout << "Press Ctrl+C to stop" << std::endl;
    std::cout << "---" << std::endl;
    
    // Main loop - run until signal
    while (g_running && bus.is_running()) {
        bus.step(std::chrono::milliseconds(100));
    }
    
    // Graceful shutdown
    std::cout << "Stopping..." << std::endl;
    auto err = bus.stop(std::chrono::seconds(5));
    if (err) {
        std::cerr << "Stop error: " << err.message() << std::endl;
    }
    
    auto stats = bus.stats();
    std::cout << "Stats: in=" << stats.messages_in 
              << " out=" << stats.messages_out << std::endl;
    std::cout << "Stopped." << std::endl;
    
    return 0;
}
