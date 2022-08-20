#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit
set -o xtrace

echo "CI: ${CI:-___XXX___}"
pwd
./build/bin/code_forensics --help

if [ ! -e /tmp/nimskull ]; then
    git clone https://github.com/nim-works/nimskull.git /tmp/nimskull
fi

rm -f nimskull.sqlite
./build/bin/code_forensics /tmp/nimskull \
    --filter-script=scripts/code_filter.py \
    --branch=devel \
    --logfile=nimskull.log \
    --outfile=nimskull.sqlite

./scripts/table_per_period.py nimskull.sqlite nimskull_burndown.png
./scripts/code_authorship.py nimskull.sqlite nimskull_authorship.png

if [ ! -e /tmp/nim ]; then
    git clone https://github.com/nim-lang/Nim.git /tmp/nim
fi

rm -f nim.sqlite
./build/bin/code_forensics /tmp/nim \
    --filter-script=scripts/code_filter.py \
    --branch=devel \
    --logfile=nim.log \
    --outfile=nim.sqlite

./scripts/table_per_period.py nim.sqlite nim_burndown.png
./scripts/code_authorship.py nim.sqlite nim_authorship.png
