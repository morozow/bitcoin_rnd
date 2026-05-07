/**
 * @file stub.c
 * @brief Stub implementation of libstdio_bus C API for environments where
 *        the real library is not available (e.g., Docker eBPF benchmark).
 *
 * All functions return error/no-op. The Bus::Start() in StdioBusSdkHooks
 * will fail gracefully and hooks will remain disabled.
 */

#include <stdio_bus_embed.h>
#include <stdlib.h>
#include <string.h>

struct stdio_bus {
    stdio_bus_state_t state;
    stdio_bus_stats_t stats;
};

stdio_bus_t *stdio_bus_create(const stdio_bus_options_t *options) {
    (void)options;
    struct stdio_bus *bus = (struct stdio_bus *)calloc(1, sizeof(struct stdio_bus));
    if (bus) bus->state = STDIO_BUS_STATE_CREATED;
    return bus;
}

void stdio_bus_destroy(stdio_bus_t *bus) {
    free(bus);
}

int stdio_bus_start(stdio_bus_t *bus) {
    if (!bus) return STDIO_BUS_ERR;
    /* Stub: cannot actually start — return error so hooks stay disabled */
    return STDIO_BUS_ERR_CONFIG;
}

int stdio_bus_stop(stdio_bus_t *bus, int timeout_sec) {
    (void)timeout_sec;
    if (!bus) return STDIO_BUS_ERR;
    bus->state = STDIO_BUS_STATE_STOPPED;
    return STDIO_BUS_OK;
}

int stdio_bus_step(stdio_bus_t *bus, int timeout_ms) {
    (void)bus; (void)timeout_ms;
    return STDIO_BUS_EOF;
}

int stdio_bus_ingest(stdio_bus_t *bus, const char *msg, size_t len) {
    (void)bus; (void)msg; (void)len;
    return STDIO_BUS_ERR;
}

stdio_bus_state_t stdio_bus_get_state(const stdio_bus_t *bus) {
    if (!bus) return STDIO_BUS_STATE_STOPPED;
    return bus->state;
}

void stdio_bus_get_stats(const stdio_bus_t *bus, stdio_bus_stats_t *stats) {
    if (bus && stats) {
        *stats = bus->stats;
    } else if (stats) {
        memset(stats, 0, sizeof(*stats));
    }
}

int stdio_bus_worker_count(const stdio_bus_t *bus) { (void)bus; return 0; }
int stdio_bus_session_count(const stdio_bus_t *bus) { (void)bus; return 0; }
int stdio_bus_pending_count(const stdio_bus_t *bus) { (void)bus; return 0; }
int stdio_bus_client_count(const stdio_bus_t *bus) { (void)bus; return 0; }
int stdio_bus_get_poll_fd(const stdio_bus_t *bus) { (void)bus; return -1; }
