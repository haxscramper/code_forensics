#!/usr/bin/env python

from cli_common import *
import matplotlib.pyplot as plt
import pandas as pd
import sqlite3

parser = init_parser()
add_rename_args(parser)
add_ignore_args(parser)
args = parser.parse_args()

df = pd.read_sql_query(
    """
select name, hash, time, message
from rcommit
inner join author on author.id == rcommit.author;
    """,
    sqlite3.connect(args.database),
)

df = df.sort_values(by=["time"])
df["name"] = df["name"].apply(lambda name: remap_name(args, name))
df["time"] = pd.to_datetime(df["time"], unit="s")
df["len"] = df["message"].apply(lambda msg: len(msg))
df = df.drop("message", axis=1)
df = df.loc[
    lambda row: row["name"].apply(lambda name: name not in set(args.ignore or []))
]

cap_max = df["len"].quantile(0.99)
df = df[df["len"] < cap_max]


df = df[["name", "time", "len"]]
df = df.set_index("time")
# df["len"] = df["len"].ewm(span=60).mean()
gb = df.groupby("name")
gb = (
    gb.size()
    .to_frame("count")
    .join(gb["len"].agg(mean=np.mean))
    .join(gb["len"].agg(min=lambda x: x.loc[lambda it: x.quantile(0.01) < it].min()))
    .join(gb["len"].agg(max=lambda x: x.loc[lambda it: it < x.quantile(0.99)].max()))
    .sort_values(by="count")
    .reset_index()
)


gb["mix"] = gb.apply(lambda row: row["mean"] * row["count"], axis=1)

gb = gb[gb["count"].quantile(0.90) < gb["count"]]
print(gb)

gb = gb.sort_values(by="mean")

fig, ax = plt.subplots(figsize=(16, 14))

ax.errorbar(
    gb["mean"],
    gb["name"],
    xerr=(gb["mean"] - gb["min"], gb["max"] - gb["mean"]),
    fmt="b",
    ecolor="blue",
)
ax.set_title("average commit message length per contributor")
# ax = gb.plot(x="name", y="len", figsize=(16, 12))

# ax = df.plot(y="len", figsize=(16, 12))
# ax.grid(True)
# ax.set_ylabel("Character count")
# ax.set_title(
#     "Number of characters in the commit message, 99th percentile, rolling 50 average"
# )

ax.grid(True)
fig.set_dpi(300)
fig.savefig(args.outfile, bbox_inches="tight")
