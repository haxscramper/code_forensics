#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit
set -x

mkdir nimskull_plots
./scripts/all_stats.py \
    nimskull.sqlite \
    nimskull_plots \
    --config=scripts/all_config.yaml \
    --subconfig=scripts/config.cfg
