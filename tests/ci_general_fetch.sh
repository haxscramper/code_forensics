#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit
set -x

echo $PWD
cd ..
echo $PWD
git config --global --add safe.directory $PWD/code_forensics
git clone https://github.com/haxscramper/code_forensics.git
echo $PWD
cd code_forensics
git submodule update --init --recursive
echo $PWD
