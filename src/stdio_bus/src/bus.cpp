/**
 * @file bus.cpp
 * @brief Implementation of stdiobus::Bus class
 */

#include <stdiobus/bus.hpp>
#include <cstring>

namespace stdiobus {

/**
 * @brief Internal implementation struct
 * 
 * Holds the C handle and callback storage.
 * Callbacks are stored here so they outlive the C API calls.
 */
struct Bus::Impl {
    stdio_bus_t* handle = nullptr;
    Options options;
    
    // Static callback trampolines
    static void message_trampoline(stdio_bus_t*, const char* msg, size_t len, void* ud) {
        auto* impl = static_cast<Impl*>(ud);
        if (impl->options.on_message) {
            impl->options.on_message(std::string_view(msg, len));
        }
    }
    
    static void error_trampoline(stdio_bus_t*, int code, const char* msg, void* ud) {
        auto* impl = static_cast<Impl*>(ud);
        if (impl->options.on_error) {
            impl->options.on_error(static_cast<ErrorCode>(code), msg ? msg : "");
        }
    }
    
    static void log_trampoline(stdio_bus_t*, int level, const char* msg, void* ud) {
        auto* impl = static_cast<Impl*>(ud);
        if (impl->options.on_log) {
            impl->options.on_log(level, msg ? msg : "");
        }
    }
    
    static void worker_trampoline(stdio_bus_t*, int worker_id, const char* event, void* ud) {
        auto* impl = static_cast<Impl*>(ud);
        if (impl->options.on_worker) {
            impl->options.on_worker(worker_id, event ? event : "");
        }
    }
    
    static void client_connect_trampoline(stdio_bus_t*, int client_id, const char* peer, void* ud) {
        auto* impl = static_cast<Impl*>(ud);
        if (impl->options.on_client_connect) {
            impl->options.on_client_connect(client_id, peer ? peer : "");
        }
    }
    
    static void client_disconnect_trampoline(stdio_bus_t*, int client_id, const char* reason, void* ud) {
        auto* impl = static_cast<Impl*>(ud);
        if (impl->options.on_client_disconnect) {
            impl->options.on_client_disconnect(client_id, reason ? reason : "");
        }
    }
};

Bus::Bus(std::string_view config_path) 
    : Bus(Options{.config_path = std::string(config_path)}) 
{}

Bus::Bus(Options options) : impl_(std::make_unique<Impl>()) {
    impl_->options = std::move(options);
    
    // Build C options struct
    stdio_bus_options_t c_opts{};
    
    if (!impl_->options.config_path.empty()) {
        c_opts.config_path = impl_->options.config_path.c_str();
    }
    if (!impl_->options.config_json.empty()) {
        c_opts.config_json = impl_->options.config_json.c_str();
    }
    
    // Listener config
    c_opts.listener.mode = static_cast<stdio_bus_listen_mode_t>(impl_->options.listener.mode);
    if (!impl_->options.listener.tcp_host.empty()) {
        c_opts.listener.tcp_host = impl_->options.listener.tcp_host.c_str();
    }
    c_opts.listener.tcp_port = impl_->options.listener.tcp_port;
    if (!impl_->options.listener.unix_path.empty()) {
        c_opts.listener.unix_path = impl_->options.listener.unix_path.c_str();
    }
    
    // Callbacks - always set trampolines, they check if callback is set
    c_opts.on_message = Impl::message_trampoline;
    c_opts.on_error = Impl::error_trampoline;
    c_opts.on_log = Impl::log_trampoline;
    c_opts.on_worker = Impl::worker_trampoline;
    c_opts.on_client_connect = Impl::client_connect_trampoline;
    c_opts.on_client_disconnect = Impl::client_disconnect_trampoline;
    
    c_opts.user_data = impl_.get();
    c_opts.log_level = impl_->options.log_level;
    
    // Create the bus
    impl_->handle = stdio_bus_create(&c_opts);
}

Bus::~Bus() {
    if (impl_ && impl_->handle) {
        // Stop if running
        auto s = stdio_bus_get_state(impl_->handle);
        if (s == STDIO_BUS_STATE_RUNNING || s == STDIO_BUS_STATE_STARTING) {
            stdio_bus_stop(impl_->handle, 5);
        }
        stdio_bus_destroy(impl_->handle);
        impl_->handle = nullptr;
    }
}

Bus::Bus(Bus&& other) noexcept : impl_(std::move(other.impl_)) {}

Bus& Bus::operator=(Bus&& other) noexcept {
    if (this != &other) {
        impl_ = std::move(other.impl_);
    }
    return *this;
}

Error Bus::start() {
    if (!impl_ || !impl_->handle) {
        return Error(ErrorCode::Invalid, "Bus not initialized");
    }
    int rc = stdio_bus_start(impl_->handle);
    return Error::from_c(rc);
}

int Bus::step(Duration timeout) {
    if (!impl_ || !impl_->handle) {
        return static_cast<int>(ErrorCode::Invalid);
    }
    return stdio_bus_step(impl_->handle, static_cast<int>(timeout.count()));
}

Error Bus::stop(std::chrono::seconds timeout) {
    if (!impl_ || !impl_->handle) {
        return Error(ErrorCode::Invalid, "Bus not initialized");
    }
    int rc = stdio_bus_stop(impl_->handle, static_cast<int>(timeout.count()));
    return Error::from_c(rc);
}

Error Bus::send(std::string_view message) {
    if (!impl_ || !impl_->handle) {
        return Error(ErrorCode::Invalid, "Bus not initialized");
    }
    int rc = stdio_bus_ingest(impl_->handle, message.data(), message.size());
    return Error::from_c(rc);
}

State Bus::state() const {
    if (!impl_ || !impl_->handle) {
        return State::Stopped;
    }
    return static_cast<State>(stdio_bus_get_state(impl_->handle));
}

Stats Bus::stats() const {
    Stats result{};
    if (impl_ && impl_->handle) {
        stdio_bus_stats_t c_stats{};
        stdio_bus_get_stats(impl_->handle, &c_stats);
        result = ffi::to_stats(c_stats);
    }
    return result;
}

int Bus::worker_count() const {
    if (!impl_ || !impl_->handle) return 0;
    return stdio_bus_worker_count(impl_->handle);
}

int Bus::session_count() const {
    if (!impl_ || !impl_->handle) return 0;
    return stdio_bus_session_count(impl_->handle);
}

int Bus::pending_count() const {
    if (!impl_ || !impl_->handle) return 0;
    return stdio_bus_pending_count(impl_->handle);
}

int Bus::client_count() const {
    if (!impl_ || !impl_->handle) return 0;
    return stdio_bus_client_count(impl_->handle);
}

int Bus::poll_fd() const {
    if (!impl_ || !impl_->handle) return -1;
    return stdio_bus_get_poll_fd(impl_->handle);
}

void Bus::on_message(MessageCallback cb) {
    if (impl_) impl_->options.on_message = std::move(cb);
}

void Bus::on_error(ErrorCallback cb) {
    if (impl_) impl_->options.on_error = std::move(cb);
}

void Bus::on_log(LogCallback cb) {
    if (impl_) impl_->options.on_log = std::move(cb);
}

void Bus::on_worker(WorkerCallback cb) {
    if (impl_) impl_->options.on_worker = std::move(cb);
}

void Bus::on_client_connect(ClientConnectCallback cb) {
    if (impl_) impl_->options.on_client_connect = std::move(cb);
}

void Bus::on_client_disconnect(ClientDisconnectCallback cb) {
    if (impl_) impl_->options.on_client_disconnect = std::move(cb);
}

stdio_bus_t* Bus::raw_handle() const {
    return impl_ ? impl_->handle : nullptr;
}

} // namespace stdiobus
