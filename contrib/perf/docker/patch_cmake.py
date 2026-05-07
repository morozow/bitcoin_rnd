#!/usr/bin/env python3
import sys
with open("src/CMakeLists.txt", "r") as f:
    content = f.read()
old_marker = 'set(STDIO_BUS_LIB_PATH "$ENV{HOME}/Projects'
if old_marker not in content:
    print("Already patched or marker not found")
    sys.exit(0)
lines = content.split('\n')
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if '# stdio_bus SDK integration' in line:
        start_idx = i
    if start_idx is not None and 'endif()' in line and i > start_idx + 3:
        end_idx = i
        break
if start_idx is None or end_idx is None:
    print("ERROR: could not find stdio_bus block boundaries")
    sys.exit(1)
new_block = '''# stdio_bus SDK integration
target_include_directories(bitcoin_node PRIVATE
  ${PROJECT_SOURCE_DIR}/src/stdio_bus/include
)
if(DEFINED STDIO_BUS_LIB_OVERRIDE AND EXISTS "${STDIO_BUS_LIB_OVERRIDE}")
  target_link_libraries(bitcoin_node PRIVATE ${STDIO_BUS_LIB_OVERRIDE})
  message(STATUS "stdio_bus: Linked override from ${STDIO_BUS_LIB_OVERRIDE}")
else()
  set(STDIO_BUS_LIB_PATH "$ENV{HOME}/Projects/Target-Insight-Function/stdio-Bus/stdiobus-sdk/stdiobus-rust/crates/stdiobus-backend-native/lib/aarch64-apple-darwin/libstdio_bus.a")
  if(EXISTS ${STDIO_BUS_LIB_PATH})
    target_link_libraries(bitcoin_node PRIVATE ${STDIO_BUS_LIB_PATH})
    message(STATUS "stdio_bus: Linked real libstdio_bus.a")
  else()
    target_sources(bitcoin_node PRIVATE ${PROJECT_SOURCE_DIR}/src/stdio_bus/src/stub.c)
    message(STATUS "stdio_bus: Using stub (libstdio_bus.a not found)")
  endif()
endif()'''
lines[start_idx:end_idx+1] = new_block.split('\n')
with open("src/CMakeLists.txt", "w") as f:
    f.write('\n'.join(lines))
print(f"OK: patched lines {start_idx}-{end_idx}")
