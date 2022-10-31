#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit

if [ ! -e /tmp/nimskull ]; then
    git clone https://github.com/nim-works/nimskull.git /tmp/nimskull
fi

./build/bin/code_forensics \
    /tmp/nimskull \
    --filter-script=scripts/code_filter.py \
    --branch=devel \
    --logfile=nimskull.log \
    --outfile=nimskull.sqlite
