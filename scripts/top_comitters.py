#!/usr/bin/env python

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from cli_common import *

parser = init_parser()
add_rename_args(parser)
add_ignore_args(parser)
add_config_args(parser)
add_title_args(parser, "Top comitter distribution")

args = parse_args_with_config(parser)

df = pd.read_sql_query(
    """
    select name from rcommit inner join
    author on rcommit.author == author.id;
    """,
    sqlite3.connect(args.database),
)
df["name"] = df["name"].apply(lambda name: remap_name(args, name))
gb = df.groupby("name")
df = gb.size().to_frame("count").sort_values(by=["count"]).reset_index()
df = df[df["count"].quantile(0.90) < df["count"]]
df["name"] = df.apply(lambda row: f"{row['name']} ({row['count']})", axis=1)
print(df)

fig, ax = plt.subplots(figsize=(16, 16))
ax.plot(df["count"], df["name"])
ax.grid(True)
ax.set_title(args.title)
ax.set_xlabel("Commit count")
ax.set_ylabel("contributor name and commit count")
fig.savefig(args.outfile, bbox_inches="tight", dpi=300)
