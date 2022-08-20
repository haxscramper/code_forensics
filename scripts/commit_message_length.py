#!/usr/bin/env python

from cli_common import *
import matplotlib.pyplot as plt
import pandas as pd
import sqlite3

parser = init_parser()
args = parser.parse_args()

df = pd.read_sql_query(
    "select hash, time, message from rcommit;", sqlite3.connect(args.database)
)

df = df.sort_values(by=["time"])
df["time"] = from_timestamps(df["time"])
df["len"] = [len(msg) for msg in df["message"]]
df = df.drop("message", axis=1)

fig = plt.figure(figsize=(16, 12), dpi=300)
ax = fig.add_subplot()

cap_max = df["len"].quantile(0.99)
df = df[df["len"] < cap_max]

plt.plot(df["time"], df["len"].ewm(span=40).mean())
plt.grid(True)
plt.ylabel("Character count")
plt.title(
    "Number of characters in the commit message, 99th percentile, rolling 50 average"
)

format_x_dates(ax)
fig.autofmt_xdate()
plt.savefig(args.outfile, bbox_inches="tight")
