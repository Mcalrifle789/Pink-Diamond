cmake_minimum_required(VERSION 3.16)
project(pink_diamond_core CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(pd_ad_engine SHARED ad_engine.cpp)
target_compile_definitions(pd_ad_engine PRIVATE PD_AD_ENGINE_EXPORTS)

add_executable(pd_ad_engine_cli ad_engine.cpp)
target_compile_definitions(pd_ad_engine_cli PRIVATE PD_AD_ENGINE_CLI)
