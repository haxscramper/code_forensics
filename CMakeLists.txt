cmake_minimum_required(VERSION 3.5)

project(code_forensics LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CONAN_DISABLE_CHECK_COMPILER ON)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/lib)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/lib)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/bin)
set(CMAKE_CXX_COMPILER clang++)
# Treat included conan libraries as a system headers - ignore warnings.
set(CONAN_SYSTEM_INCLUDES ON)

# Otherwise boost compilation fails to work due to internal compilation errors.
# No, 'SYSTEM_INCLUDES' does not help.
add_compile_options(-Wno-c++11-narrowing)
add_compile_options(-Wno-deprecated-declarations)

set(DEPS_DIR ${CMAKE_SOURCE_DIR}/build/dependencies/conan)
list(PREPEND CMAKE_MODULE_PATH ${DEPS_DIR})
include(${DEPS_DIR}/conanbuildinfo.cmake)
conan_basic_setup()

find_package(Python REQUIRED COMPONENTS Development)
find_package(Boost REQUIRED COMPONENTS system program_options python thread log)
find_package(SqliteOrm REQUIRED)
find_package(fmt REQUIRED)
find_package(libgit2 REQUIRED)
find_package(SQLite3 REQUIRED)

add_compile_options(-ferror-limit=1)
add_compile_options(-fcoroutines-ts)

add_compile_options(-Wno-format-security)
add_compile_options(-Wno-c99-designator)
add_executable(code_forensics code_forensics.cpp)

# Documentation says I can use `conan_basic_setup` and `CONAN_LIBS`, but this
# does not work - I consistently end up with a linker error.
target_link_libraries(
  code_forensics
  PUBLIC fmt::fmt
         Python::Python
         Boost::system
         Boost::python
         Boost::program_options
         Boost::thread
         Boost::log
         SQLite::SQLite
         libgit2::libgit2)

target_include_directories(
  code_forensics PUBLIC Python::Python Boost::system Boost::program_options
                        SqliteOrm::sqlite_orm)
