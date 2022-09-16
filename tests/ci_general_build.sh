#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit
set -x

mkdir -p build
cd build
cmake ..
make -j10
cd ..
