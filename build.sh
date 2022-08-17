#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit

function py_plotter() {
    ./scripts/table_per_period.py /tmp/db.sqlite /tmp/db.png
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
    cmake ..
    make -j12
    popd
}

bin=./build/bin/code_forensics

function debug_run() {
    echo "git user compile ok"
    OPTS="/tmp/nimskull --log-progress=false --branch=devel --filter-script=../scripts/code_filter.py"
    bin --help || gdb_cmd bin --help
    bin $OPTS || gdb_cmd bin $OPTS
    echo "git user run ok"
}

CONAN_DIR="$ROOT/build/dependencies/conan"

function build_git_wrapper() {
    clang++ generate_git_wrapper/genwrapper.cpp \
        -std=c++2a \
        -ferror-limit=1 \
        -o genwrapper.bin \
        -fuse-ld=mold \
        -g \
        -lclang-cpp \
        -lLLVM \
        @"$CONAN_DIR/conanbuildinfo.gcc"

}

function wrap_git() {
    path=$(
        jq -r \
            '.dependencies[] | select(.name == "libgit2") | .include_paths[0]' \
            "$CONAN_DIR/conanbuildinfo.json"
    )

    ./genwrapper.bin \
        $path/git2.h \
        -o=$PWD/src/gitwrap.hpp \
        --conf=$PWD/generate_git_wrapper/wrapconf.yaml \
        -extra-arg=-I/usr/lib/clang/14.0.6/include

}

function conan_install() {
    conan install . -if build/dependencies/conan --build=missing --settings compiler.libcxx="libstdc++11"
}

CI=true

# try_build
# build_git_wrapper
# wrap_git
# conan_install
try_build
export CI
./tests/ci_compare_repo.sh
# py_plotter
# cmake .
# make -j 12
