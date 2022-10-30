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
    times = {}

    if True:
        # TODO add configuration argument to implement different
        # mapping strategies
        times = {"comment": [], "pull": [], "issue": [], "issue_event": []}

        for name, time in times.items():
            for it in con.execute(sqa.select(meta.tables["comment"])):
                time.append(it.created_at)

    elif False:
        created = []
        closed = []
        for it in con.execute(sqa.select(meta.tables["issue"])):
            created.append(it.created_at)
            if it.closed_at:
                closed.append(it.closed_at)

        times = {"created": created, "closed": closed}

    else:
        created = []
        closed = []
        for it in con.execute(sqa.select(meta.tables["pull"])):
            created.append(it.created_at)
            if it.closed_at:
                closed.append(it.closed_at)

        times = {"created": created, "closed": closed}

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
    label = [name for name, _ in times.items()]
    value = [it[0] for it in histogram_data]
    xdata = histogram_data[0][1][:-1]
    items = len(times)
    width = np.min(np.diff(xdata)) * 0.7

    if False:
        for idx in range(items):
            if 0 < idx:
                value[idx] += value[idx - 1]

        ax.stackplot(xdata, value, labels=label)

    else:
        bottom = np.cumsum(
            [np.zeros(len(value[0])).astype(int)] + value, axis=0
        )

        for idx in range(items):
            ax.bar(
                x=xdata,
                height=value[idx],
                bottom=bottom[idx],
                label=label[idx],
                width=width,
                edgecolor="black",
            )

    ax.grid(True)
    cli.format_x_dates(ax)
    ax.legend(loc="upper left")
    fig.savefig(args.outfile, dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    plt.rcParams["font.family"] = "consolas"

    if len(sys.argv) == 1:
        impl(parse_args(["parse_github_copy.sqlite", "info.png"]))
    else:
        impl(parse_args())
