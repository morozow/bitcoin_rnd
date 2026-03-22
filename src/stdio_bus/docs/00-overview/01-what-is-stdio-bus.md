# What is stdio_bus?

## Purpose

stdio_bus is a **deterministic transport layer** for AI agent protocols (ACP/MCP). It provides:

- **Process supervision**: Manages worker process lifecycle (spawn, monitor, restart)
- **Message routing**: Routes JSON-RPC messages between clients and workers
- **Session management**: Maintains session affinity for stateful conversations
- **Backpressure control**: Prevents memory exhaustion under load

## What stdio_bus is NOT

- ❌ Not an AI/ML framework
- ❌ Not a message queue (no persistence)
- ❌ Not a protocol implementation (protocol-agnostic)
- ❌ Not multi-threaded (single event loop by design)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Host Application                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   C++ SDK (stdiobus)                 │    │
│  │  ┌─────────┐  ┌──────────┐  ┌─────────────────┐    │    │
│  │  │   Bus   │  │ AsyncBus │  │   BusBuilder    │    │    │
│  │  └────┬────┘  └────┬─────┘  └────────┬────────┘    │    │
│  │       └────────────┴──────────────────┘             │    │
│  │                      │                              │    │
│  │              ┌───────┴───────┐                      │    │
│  │              │   FFI Layer   │                      │    │
│  │              └───────┬───────┘                      │    │
│  └──────────────────────┼──────────────────────────────┘    │
│                         │                                    │
│              ┌──────────┴──────────┐                        │
│              │  libstdio_bus.a (C) │                        │
│              └──────────┬──────────┘                        │
└─────────────────────────┼───────────────────────────────────┘
                          │ stdin/stdout pipes
         ┌────────────────┼────────────────┐
         │                │                │
    ┌────┴────┐     ┌─────┴─────┐    ┌─────┴─────┐
    │ Worker 1│     │  Worker 2 │    │  Worker N │
    │ (ACP)   │     │   (ACP)   │    │   (ACP)   │
    └─────────┘     └───────────┘    └───────────┘
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Single-threaded | Deterministic behavior, no race conditions |
| Non-blocking I/O | Responsive event loop, no deadlocks |
| No external deps | Minimal attack surface, easy embedding |
| Protocol agnostic | Forward messages unchanged, parse only routing fields |
| NDJSON framing | Simple, debuggable, streaming-friendly |

## Message Flow

```
Client Request                    Worker Response
     │                                  │
     ▼                                  │
┌─────────┐                             │
│ Ingest  │ Parse sessionId, id         │
└────┬────┘                             │
     │                                  │
     ▼                                  │
┌─────────┐                             │
│ Route   │ Session → Worker mapping    │
└────┬────┘                             │
     │                                  │
     ▼                                  │
┌─────────┐    stdin    ┌─────────┐     │
│ Queue   │────────────▶│ Worker  │     │
└─────────┘             └────┬────┘     │
                             │ stdout   │
                             ▼          │
                        ┌─────────┐     │
                        │ Receive │     │
                        └────┬────┘     │
                             │          │
                             ▼          │
                        ┌─────────┐     │
                        │Correlate│ Match response.id
                        └────┬────┘     │
                             │          │
                             ▼          │
                        ┌─────────┐     │
                        │Callback │─────┘
                        └─────────┘
```

## When to Use stdio_bus

✅ **Good fit:**
- Local AI tool runtime (MCP servers)
- Agent orchestration with session state
- High-throughput message routing
- Cross-language worker pools
- Deterministic replay/audit requirements

❌ **Not ideal for:**
- Distributed multi-host deployments (use TCP mode with care)
- Persistent message queuing (use Kafka/RabbitMQ)
- Request/response with >10s latency (use async patterns)
