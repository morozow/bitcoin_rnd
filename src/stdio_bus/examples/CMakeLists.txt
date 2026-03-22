add_executable(basic_example basic.cpp)
target_link_libraries(basic_example PRIVATE stdiobus)

add_executable(async_example async.cpp)
target_link_libraries(async_example PRIVATE stdiobus)

add_executable(builder_example builder.cpp)
target_link_libraries(builder_example PRIVATE stdiobus)
