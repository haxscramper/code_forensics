#!/usr/bin/env python

import pandas as pd
import math
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "consolas"

from cli_common import *

parser = init_parser()
parser.add_argument(
    "--subdir-breakdown",
    dest="subdir_breakdown",
    type=bool,
    default=False,
    help="Create per-subdirectory division or group all elements in one distribution",
)
args = parser.parse_args()

con = sqlite3.connect(args.database)
cur = con.cursor()


def content_category(content: str) -> int:
    if "##" in content:
        return 1

    elif len(content.strip()) == 0:
        return 2

    else:
        return 0


category_map = {}
content_map = {}

for (id, text) in cur.execute("select id, text from strings;"):
    category_map[id] = content_category(text)
    content_map[id] = text

df = pd.read_sql_query(
    open(Path(__file__).parent / "line_category.sql").read(),
    con,
)

time = df["commit_time"].max()

df = df[df["commit_time"] == time]
df["category"] = df["content"].apply(lambda content: category_map[content])
df["text"] = df["content"].apply(lambda it: content_map[it])
df["file_path"] = df["file_dir"] + df["file_name"]
df = (
    df.groupby(["file_dir", "file_name"])
    .agg(
        comment=("category", lambda x: x.loc[x == 1].count()),
        code=("category", lambda x: x.loc[x == 0].count()),
        empty=("category", lambda x: x.loc[x == 2].count()),
        dir=("file_dir", lambda x: x.drop_duplicates().iloc[0]),
    )
    .reset_index()
)

fig, ax = plt.subplots(figsize=(16, 34))
ax.invert_yaxis()
df["total"] = df["code"] + df["comment"]

if args.subdir_breakdown:
    df = df.sort_values(["dir", "total"], ascending=False)

    max_total = int(math.log(df["total"].max(), 10) + 1)
    max_name = df["file_name"].apply(lambda x: len(x)).max()
    max_dir = df["file_dir"].apply(lambda x: len(x)).max()

    df["name"] = df.apply(
        lambda row: f"{row['file_dir']:-<{max_dir}}"
        + f"{row['file_name']:->{max_name}} "
        + f"({row['total']:<{max_total}})",
        axis=1,
    )

else:
    df = df.sort_values("total", ascending=False)
    df["name"] = df.apply(lambda row: row["file_dir"] + row["file_name"], axis=1)

ax.barh(df["name"], df["comment"], color="green", edgecolor="black", label="Code count")

ax.barh(
    df["name"],
    df["code"],
    left=df["comment"],
    color="blue",
    edgecolor="black",
    label="Code count",
)

ax.barh(
    df["name"],
    df["empty"],
    left=df["comment"] + df["code"],
    color="gray",
    label="Empty",
)

ax.grid(True)
ax.legend(loc="lower right")
ax.set_xlabel("Line count")
comment_percent = df["comment"].sum() / df["code"].sum()
ax.set_title(
    f"Line category breakdown, code total is {df['code'].sum()}, "
    + f"comment total is {df['comment'].sum()} ({comment_percent:4.3}%) "
    + f"empty {df['empty'].sum()}"
)
fig.savefig(args.outfile, bbox_inches="tight", dpi=300)
