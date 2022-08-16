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

include(${CMAKE_SOURCE_DIR}/conanbuildinfo.cmake)
conan_basic_setup()

find_package(
  Boost
  COMPONENTS system filesystem thread log program_options python
  REQUIRED)
find_package(
  Python
  COMPONENTS Interpreter Development
  REQUIRED)

add_compile_options(-ggdb)

# add_compile_options(-fmax-errors=1) add_compile_options(-fcoroutines)
add_compile_options(-ferror-limit=1)
add_compile_options(-fcoroutines-ts)

add_compile_options(-Wno-format-security)
add_compile_options(-Wno-c99-designator)
add_executable(code_forensics code_forensics.cpp)

target_link_libraries(code_forensics matplot)

target_link_libraries(code_forensics ${Boost_LIBRARIES})
target_link_libraries(code_forensics ${CONAN_LIBS})
target_link_libraries(code_forensics ${Python_LIBRARIES})

target_link_directories(code_forensics PRIVATE ${CONAN_LIB_DIRS})
target_link_directories(code_forensics PRIVATE ${Boost_LIBRARY_DIRS})
target_link_directories(code_forensics PRIVATE ${Python_LIBRARY_DIRS})

target_include_directories(code_forensics PRIVATE ${Boost_INCLUDE_DIRS})
target_include_directories(code_forensics PRIVATE ${CONAN_INCLUDE_DIRS})
target_include_directories(code_forensics PRIVATE ${Python_INCLUDE_DIRS})

# set_target_properties(code_forensics PROPERTIES RUNTIME_OUTPUT_DIRECTORY
# "${CMAKE_SOURCE_DIR}")
