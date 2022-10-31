#!/usr/bin/env bash
# -*- coding: utf-8 -*-
set -o nounset
set -o errexit
set -x

./.github/workflows/ci_general_deps.sh
./.github/workflows/ci_general_build.sh
./.github/workflows/ci_build_db.sh
./.github/workflows/ci_general_run.sh
