#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct 30 16:58:42 2022

@author: haxscramper
"""

import cli_common as cli
import matplotlib.pyplot as plt
import sqlalchemy as sqa
import numpy as np
import sys
from parse_github_sql_schema import *


def parse_args(args=sys.argv[1:]):
    parser = cli.init_parser()
    parser.add_argument(
        "--top",
        dest="top",
        default=15,
        type=int,
        help="How many committers from the top to plot",
    )

    return cli.parse_args_with_config(parser, args)


def impl(args):
    engine = sqa.create_engine(f"sqlite:///{args.database}")
    Session = sqa.orm.sessionmaker(bind=engine)
    session = Session()
    meta = SQLBase.metadata
    con = engine.connect()

    times = {"comment": [], "pull": [], "issue": []}

    for name, time in times.items():
        for it in con.execute(sqa.select(meta.tables["comment"])):
            time.append(it.created_at)

    for name, time in times.items():
        time = sorted(time)

    range_min = 1024 * 1024 * 1024 * 1024
    range_max = 0

    for name, time in times.items():
        range_min = min(range_min, min(time))
        range_max = max(range_max, max(time))

    (range_min, range_max) = cli.from_timestamps([range_min, range_max])

    histogram_data = []
    for name, time in times.items():
        dates = cli.from_timestamps(time)
        histogram_data.append(
            np.histogram(dates, bins=60, range=(range_min, range_max))
        )

    fig, ax = plt.subplots(figsize=(12, 12))
    ax.stackplot(
        histogram_data[0][1][:-1],
        [it[0] for it in histogram_data],
        labels=[name for name, _ in times.items()],
    )

    ax.grid(True)
    cli.format_x_dates(ax)
    fig.legend()
    fig.savefig(args.outfile, dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    plt.rcParams["font.family"] = "consolas"

    if len(sys.argv) == 1:
        impl(parse_args(["parse_github_copy.sqlite", "info.png"]))
    else:
        impl(parse_args())
