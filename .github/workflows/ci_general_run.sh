#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit
set -x

git clone https://github.com/nim-works/nimskull.git /tmp/nimskull
./build/bin/code_forensics \
    /tmp/nimskull \
    --filter-script=scripts/code_filter.py \
    --branch=devel \
    --logfile=nimskull.log \
    --outfile=nimskull.sqlite

mkdir nimskull_plots
./scripts/all_stats.py \
    nimskull.sqlite \
    nimskull_plots \
    --config=scripts/all_config.yaml \
    --subconfig=scripts/config.cfg
