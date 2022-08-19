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
from typing import *

parser = argparse.ArgumentParser(description="Process some integers.")
parser.add_argument("database", type=str, help="Input database file")
parser.add_argument("outfile", type=str, help="Output plot image")
args = parser.parse_args()

con = sqlite3.connect(args.database)
cur = con.cursor()

authors = {}

for row in cur.execute("select author, time from commits;"):
    if row[0] not in authors:
        authors[row[0]] = []

    authors[row[0]].append(row[1])

top_authors = sorted(list(authors.items()), key=lambda it: len(it[1]), reverse=True)

topcount: int = 10


def from_timestamps(timestamps: List[int]):
    result = []
    for time in timestamps:
        result.append(date2num(datetime.utcfromtimestamp(time)))

    return result


# gs = gridspec.GridSpec(topcount, 1)
# fig = plt.figure(figsize=(16, 9))


# i = 0
# axis_objects = []
# for author, commits in top_authors[0:topcount]:
#     print(commits)

#     ax = fig.add_subplot(gs[i : i + 1, 0:])

#     axis_objects.append(ax)

#     i += 1


def num_now():
    return date2num(datetime.now())


def plot_datehist(ax, dates, bins, title=None):
    (hist, bin_edges) = np.histogram(dates, 50)
    width = bin_edges[1] - bin_edges[0]

    ax.plot(bin_edges[:-1], hist / width)
    ax.set_xlim(bin_edges[0], num_now())
    ax.set_ylabel("Events [1/day]")
    if title:
        ax.set_title(title)

    # set x-ticks in date
    # see: http://matplotlib.sourceforge.net/examples/api/date_demo.html
    ax.xaxis.set_major_locator(YearLocator())
    ax.xaxis.set_major_formatter(DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(MonthLocator())
    # format the coords message box
    ax.format_xdata = DateFormatter("%Y-%m-%d")
    ax.grid(True)


fig = plt.figure()
ax = fig.add_subplot(111)
fig.autofmt_xdate()

dates = from_timestamps(top_authors[0][1])
plot_datehist(ax, dates, 50)
plt.savefig(args.outfile, bbox_inches="tight")
