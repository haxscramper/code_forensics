#!/usr/bin/env python

from matplotlib import rcParams
import argparse

rcParams["font.family"] = "consolas"

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

parser = argparse.ArgumentParser(description="Process some integers.")
parser.add_argument("database", type=str, help="Input database file")
parser.add_argument("outfile", type=str, help="Output plot image")
parser.add_argument(
    "--rename",
    dest="rename",
    type=str,
    action="append",
    help="Name=Other pair for handling users with multiple names",
)

parser.add_argument(
    "--ignore", dest="ignore", type=str, action="append", help="List of users to ignore"
)

args = parser.parse_args()

con = sqlite3.connect(args.database)
cur = con.cursor()

authors = {}
author_names = {}

ignored_names = set(args.ignore)
remap = [(it[0], it[1]) for it in [pair.split("=") for pair in args.rename]]


def remap_name(name: str) -> str:
    for (old, new) in remap:
        if name == old:
            return new

    return name


for row in cur.execute("select id, name from author;"):
    author_names[row[0]] = remap_name(row[1])

for row in cur.execute("select author, time from commits;"):
    name = author_names[row[0]]
    if name in ignored_names:
        continue

    if name not in authors:
        authors[name] = []

    authors[name].append(row[1])

top_authors = sorted(list(authors.items()), key=lambda it: len(it[1]), reverse=True)

topcount: int = 40


def from_timestamps(timestamps: List[int]):
    result = []
    for time in timestamps:
        result.append(date2num(datetime.utcfromtimestamp(time)))

    return result


def num_now():
    return date2num(datetime.now())


gs = gridspec.GridSpec(topcount, 1)
fig = plt.figure(figsize=(16, 32), dpi=300)

min_date = None
for author, commits in top_authors[0:topcount]:
    for date in from_timestamps(commits):
        if not min_date or date < min_date:
            min_date = date


i = 0
axis_objects = []
for author, commits in top_authors[0:topcount]:
    ax = fig.add_subplot(gs[i : i + 1, 0:])

    dates = from_timestamps(commits)

    (hist, bin_edges) = np.histogram(dates, 60)

    ax.plot(bin_edges[:-1], hist)
    ax.set_xlim(min_date, num_now())
    ax.set_ylabel(author, rotation=0)

    # set x-ticks in date
    # see: http://matplotlib.sourceforge.net/examples/api/date_demo.html
    ax.xaxis.set_major_locator(YearLocator())
    ax.xaxis.set_major_formatter(DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(MonthLocator())
    # format the coords message box
    ax.format_xdata = DateFormatter("%Y-%m-%d")
    ax.set_yticklabels([])

    spines = ["top", "right", "left", "bottom"]
    for s in spines:
        ax.spines[s].set_visible(False)

    ax.grid(True)

    axis_objects.append(ax)

    i += 1


fig.autofmt_xdate()
plt.savefig(args.outfile, bbox_inches="tight")
