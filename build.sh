#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit

PER_YEAR=1

TARGET=nimskull
BRANCH=devel

function py_plotter() {
    ./scripts/table_per_period.py /tmp/db.sqlite /tmp/db.png --per-year=$PER_YEAR
    echo "py plotter ok"
}

function sql_select() {
    cat scripts/default.sql scripts/table_per_period.sql |
        sqlite3 /tmp/db.sqlite
}

ROOT=$(pwd)

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
    OPTS="/tmp/$TARGET --branch=$BRANCH --filter-script=scripts/code_filter.py --filter-args=--per-year=$PER_YEAR --filter-args=--target=$TARGET"
    $bin --help || gdb_cmd $bin --help
    $bin $OPTS || gdb_cmd $bin $OPTS
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

function generate_docs() {
    doxygen -q Doxyfile
    # dot -Tpng -o<source>.png -Tcmapx -o<source>.map <source>.dot
}

# generate_docs
# try_build
# build_git_wrapper
# wrap_git
# conan_install
try_build
debug_run
# # export CI
# ./tests/ci_compare_repo.sh
# sql_select
py_plotter
# cmake .
# make -j 12
