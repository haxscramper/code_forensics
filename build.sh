#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit

path=$(
    jq -r \
        '.dependencies[] | select(.name == "libgit2") | .include_paths[0]' \
        conanbuildinfo.json
)

function py_plotter() {
    ./table_per_period.py
    echo "py plotter ok"
}

ROOT=$(pwd)

echo "source $ROOT/gdb_decorator"
function gdb_cmd {
    gdb \
        -batch \
        -nx \
        -ex "source $ROOT/gdb_decorator.py" \
        -ex "set print address off" \
        -ex "set print frame-arguments none" \
        -ex "set print frame-info source-and-location" \
        -ex "set filename-display basename" \
        -ex "run" \
        -ex "bt" \
        --args $@

    # -ex "set print frame-arguments presence" \
}

function try_build() {
    mkdir -p build
    pushd build
    cmake .. -D "CMAKE_MODULE_PATH=$ROOT/build/dependencies/conan"
    make -j12

    echo "git user compile ok"
    OPTS="/tmp/nimskull --branch=devel --filter-script=../code_filter.py"
    ./bin/code_forensics --help
    ./bin/code_forensics $OPTS || gdb_cmd ./bin/code_forensics $OPTS
    echo "git user run ok"
    popd
}

function build_git_wrapper() {
    clang++ genwrapper.cpp \
        -std=c++2a \
        -ferror-limit=1 \
        -o genwrapper \
        -fuse-ld=mold \
        -g \
        -lclang-cpp \
        -lLLVM \
        @conanbuildinfo.gcc

}

function wrap_git() {
    ./genwrapper \
        $path/git2.h \
        -o=$PWD/code_forensics/gitwrap.hpp \
        -extra-arg=-I/usr/lib/clang/14.0.6/include

}

function conan_install() {
    conan install . -if build/dependencies/conan --build=missing --settings compiler.libcxx="libstdc++11"
}

# try_build
# build_git_wrapper
# wrap_git
conan_install
try_build
py_plotter
# cmake .
# make -j 12
