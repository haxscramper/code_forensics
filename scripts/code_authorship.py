#!/usr/bin/env python

from matplotlib import rcParams

rcParams["font.family"] = "consolas"

import argparse
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from pprint import pprint

parser = argparse.ArgumentParser(description="Process some integers.")
parser.add_argument("database", type=str, help="Input database file")
parser.add_argument("outfile", type=str, help="Output plot image")
args = parser.parse_args()
import sqlite3

con = sqlite3.connect(args.database)
cur = con.cursor()


def map_name(name: str) -> str:
    if name == "Andreas Rumpf":
        return "Araq"

    else:
        return name


total_writers = {}
all_periods = set()
author_period_map = {}


for row in cur.execute(open(Path(__file__).parent / "code_authorship.sql").read()):
    (author, period, line_count) = row
    all_periods.add(period)
    name = map_name(author)
    if name not in total_writers:
        total_writers[name] = 0

    if name not in author_period_map:
        author_period_map[name] = {}

    total_writers[name] += line_count
    if period not in author_period_map[name]:
        author_period_map[name][period] = 0

    author_period_map[name][period] += line_count

# pprint.pprint(total_writers)
authors_ordered = sorted(total_writers.items(), key=lambda it: it[1], reverse=True)
other_authors = {}

per_period = {period: 0 for period in all_periods}
for author, per_map in author_period_map.items():
    for period, count in per_map.items():
        per_period[period] += count

top_n = 15

for author, count in authors_ordered[(top_n) - 1 : -1]:
    for period in author_period_map[author]:
        if period not in other_authors:
            other_authors[period] = 0

        other_authors[period] += author_period_map[author][period]

    del author_period_map[author]


author_period_map["other"] = other_authors
total_writers["other"] = sum([count for _, count in other_authors.items()])

authors_ordered = sorted(total_writers.items(), key=lambda it: it[1], reverse=True)
for author_idx, (author, count) in enumerate(authors_ordered):
    if author in author_period_map:
        for period in sorted(all_periods):
            if period not in author_period_map[author]:
                author_period_map[author][period] = 0


sample_count: int = len(all_periods)
author_count: int = len(author_period_map)

data = np.zeros([author_count, sample_count]).astype(int)
indexed_authors = []

authors = [name for (name, _) in authors_ordered[:top_n]]

for author_idx, author in enumerate(authors):
    indexed_authors.append(author)
    for period_idx, period in enumerate(sorted(author_period_map[author].keys())):
        lines = author_period_map[author][period]
        data[author_idx][period_idx] = lines

offset = np.zeros(sample_count)
index = list(sorted(all_periods))
colors = plt.cm.rainbow(np.linspace(0, 0.8, author_count))

fig = plt.figure(figsize=(10, 12), dpi=300, constrained_layout=True)

for author_idx, samples in enumerate(data):
    if top_n - 1 < author_idx:
        break

    plt.bar(
        index,
        samples,
        width=1.0,
        bottom=offset,
        color=colors[author_idx],
        edgecolor="black",
        label=indexed_authors[author_idx],
    )

    offset = offset + samples

plt.legend(loc="upper left")
plt.savefig(args.outfile, bbox_inches="tight")
