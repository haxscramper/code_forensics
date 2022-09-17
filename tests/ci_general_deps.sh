#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit
set -x

echo $PWD
pip install conan matplotlib igraph pandas numpy

whoami
echo $PWD
conan install . \
    -if build/dependencies/conan \
    --build=missing \
    --settings compiler.libcxx="libstdc++11"
