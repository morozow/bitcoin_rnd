#!/usr/bin/env python3
"""Add new event serializers to stdio_bus_sdk_hooks.cpp"""

import re

filepath = "src/node/stdio_bus_sdk_hooks.cpp"

with open(filepath, "r") as f:
    content = f.read()

new_serializers = '''        else if constexpr (std::is_same_v<T, TxRemovedEvent>) {
            ss << "\\"type\\":\\"tx_removed\\","
                << "\\"txid\\":\\"" << arg.txid.GetHex() << "\\","
                << "\\"reason\\":\\"" << arg.reason << "\\","
                << "\\"vsize\\":" << arg.vsize << ","
                << "\\"fee\\":" << arg.fee << ","
                << "\\"timestamp_us\\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, TxReplacedEvent>) {
            ss << "\\"type\\":\\"tx_replaced\\","
                << "\\"replaced_txid\\":\\"" << arg.replaced_txid.GetHex() << "\\","
                << "\\"replaced_vsize\\":" << arg.replaced_vsize << ","
                << "\\"replaced_fee\\":" << arg.replaced_fee << ","
                << "\\"replacement_txid\\":\\"" << arg.replacement_txid.GetHex() << "\\","
                << "\\"replacement_vsize\\":" << arg.replacement_vsize << ","
                << "\\"replacement_fee\\":" << arg.replacement_fee << ","
                << "\\"timestamp_us\\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, TxRejectedEvent>) {
            ss << "\\"type\\":\\"tx_rejected\\","
                << "\\"txid\\":\\"" << arg.txid.GetHex() << "\\","
                << "\\"reason\\":\\"" << arg.reason << "\\","
                << "\\"timestamp_us\\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, UTXOCacheFlushEvent>) {
            ss << "\\"type\\":\\"utxocache_flush\\","
                << "\\"duration_us\\":" << arg.duration_us << ","
                << "\\"mode\\":" << arg.mode << ","
                << "\\"coins_count\\":" << arg.coins_count << ","
                << "\\"coins_mem_usage\\":" << arg.coins_mem_usage << ","
                << "\\"is_flush_for_prune\\":" << (arg.is_flush_for_prune ? "true" : "false") << ","
                << "\\"timestamp_us\\":" << arg.timestamp_us;
        }
        else if constexpr (std::is_same_v<T, PeerConnectionEvent>) {
            ss << "\\"type\\":\\"peer_connection\\","
                << "\\"peer_id\\":" << arg.peer_id << ","
                << "\\"addr\\":\\"" << arg.addr << "\\","
                << "\\"conn_type\\":\\"" << arg.conn_type << "\\","
                << "\\"network\\":" << arg.network << ","
                << "\\"inbound\\":" << (arg.inbound ? "true" : "false") << ","
                << "\\"timestamp_us\\":" << arg.timestamp_us;
        }
'''

# Insert before "    }, ev);"
target = "    }, ev);"
if target in content:
    content = content.replace(target, new_serializers + "    }, ev);", 1)
    with open(filepath, "w") as f:
        f.write(content)
    print("OK: Added serializers")
else:
    print("ERROR: Could not find insertion point")
