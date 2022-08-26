#!/usr/bin/env python
# https://tkf.github.io/2011/04/20/visualizing-git-and-hg-commit-activity.html
# https://matplotlib.org/matplotblog/posts/create-ridgeplots-in-matplotlib/

from matplotlib import rcParams

rcParams["font.family"] = "consolas"

import math
import argparse


from copy import deepcopy
import sqlite3
import pprint
import itertools
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.dates import YearLocator, MonthLocator, DateFormatter
from matplotlib.dates import date2num
from datetime import datetime
import numpy as np
import sys
from typing import *
from cli_common import *


def parse_args(args=sys.argv[1:]):
    parser = init_parser()
    parser.add_argument(
        "--top",
        dest="top",
        default=40,
        type=int,
        help="How many committers from the top to plot",
    )

    return parse_args_with_config(parser, args)


def impl(args):
    cur = open_db(args)

    authors = {}
    author_names = {}

    ignored_names = set(args.ignore or [])

    for row in cur.execute("select id, name from author;"):
        author_names[row[0]] = remap_name(args, row[1])

    for row in cur.execute("select author, time, added, removed from rcommit;"):
        name = author_names[row[0]]
        if name in ignored_names:
            continue

        if name not in authors:
            authors[name] = []

        authors[name].append((row[1], row[2], row[3]))

    for author, stats in authors.items():
        authors[author] = list(sorted(stats, key=lambda it: it[0]))

    top_authors = sorted(list(authors.items()), key=lambda it: len(it[1]), reverse=True)

    topcount: int = args.top

    def num_now():
        return date2num(datetime.now())

    gs = gridspec.GridSpec(topcount, 1)
    fig = plt.figure(figsize=(16, 12), dpi=300)

    min_date = None
    for author, commits in top_authors[0:topcount]:
        for date in from_timestamps([time for (time, _, _) in commits]):
            if not min_date or date < min_date:
                min_date = date

    i = 0
    axis_objects = []
    for author, commits in top_authors[0:topcount]:
        # Incrementally add subplots for the top N authors in the dataset
        ax = fig.add_subplot(gs[i : i + 1, 0:])

        # Extract dates, number of added and removed lines per each commit
        times = [time for (time, _, _) in commits]
        added = [added for (_, added, _) in commits]
        removed = [removed for (_, _, removed) in commits]
        dates = from_timestamps(times)

        bins = 60
        # Split input data into fixed histograms to reduce activity noise
        (hist, bin_edges) = np.histogram(dates, bins)

        ax.plot(bin_edges[:-1], hist)
        ax.set_xlim(min_date, num_now())
        width = int(math.log(max([len(commits), sum(added), sum(removed)]), 10)) + 1
        # For each subplot add title and align it to the top left corner
        ax.set_ylabel(
            f"{author}\n{len(commits):<{width}} "
            + f"total\n{sum(added):<{width}} added\n{sum(removed):<{width}} removed",
            rotation=0,
            labelpad=120,
            ha="left",
            va="top",
        )

        # Add common position grid
        ax.grid(True)

        # Two metrics for each plot - dates and line add/remove information
        lines = ax.twinx()

        lines.plot(dates, added, "g")
        # Plot removed line count as a negative
        lines.plot(dates, [-r for r in removed], "r")

        for it in [ax, lines]:
            format_x_dates(it)

        align_yaxis([ax, lines])
        axis_objects.append(ax)

        i += 1

    fig.autofmt_xdate()
    plt.savefig(args.outfile, bbox_inches="tight")
