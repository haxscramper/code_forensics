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


# Assign line text category information - in this case it is a simple integer value, but can be anything that dataframe can handle later on
def content_category(content: str) -> int:
    # "good enough" heuristics for detecting documentation comment lines
    if "##" in content:
        return 1

    # Empty line detection is rather straighforward
    elif len(content.strip()) == 0:
        return 2

    # Everything else is counted as code
    else:
        return 0


category_map = {}

# Create content annotation table from the string content. T
for (id, text) in cur.execute("select id, text from strings;"):
    category_map[id] = content_category(text)

# Read line category queries from the sql script
df = pd.read_sql_query(
    open(Path(__file__).parent / "line_category.sql").read(),
    con,
)

# Analyze latest commit. Later on multiple data frames can be aggregated
# together based on `groupby("commit_time")`
time = df["commit_time"].max()

df = df[df["commit_time"] == time]
df["category"] = df["content"].apply(lambda content: category_map[content])
df["file_path"] = df["file_dir"] + df["file_name"]
df = (
    # 'count' or 'total' field is not necessary here, so direct aggregate can be used
    df.groupby(["file_dir", "file_name"])
    .agg(
        # count number of lines in each category separately - number of categories is fixed (due to hardcoded detection logic), so column names can be hardcoded here as well
        comment=("category", lambda x: x.loc[x == 1].count()),
        code=("category", lambda x: x.loc[x == 0].count()),
        empty=("category", lambda x: x.loc[x == 2].count()),
        # grouped by file directories, so dropping duplicates and taking first element in series is safe here
        dir=("file_dir", lambda x: x.drop_duplicates().iloc[0]),
    )
    .reset_index()
)

fig, ax = plt.subplots(figsize=(16, 34))
ax.invert_yaxis()
df["total"] = df["code"] + df["comment"]

# If per-directory breakdown was requested - create it, otherwise use a simplified approach
if args.subdir_breakdown:
    df = df.sort_values(["dir", "total"], ascending=False)

    max_total = int(math.log(df["total"].max(), 10) + 1)
    max_name = df["file_name"].apply(lambda x: len(x)).max()

    df["name"] = df.apply(
        lambda row: f"{row['file_name']:-<{max_name}} "
        + f"({row['total']:<{max_total}})",
        axis=1,
    )

else:
    df = df.sort_values("total", ascending=False)
    max_name = (
        df["file_dir"].apply(lambda x: len(x)) + df["file_name"].apply(lambda x: len(x))
    ).max()

    def name(r):
        return (
            f"({r.comment:<4}/{r.code:<4}/{r['empty']:<4}) "
            + f"{r.file_name:-<{max_name}}"
        )

    df["name"] = df.apply(lambda row: name(row), axis=1)

# Code documentation lines are placed at the very left of the barplot
ax.barh(
    df["name"], df["comment"], color="green", edgecolor="black", label="Comment count"
)

# Then code is added on top of them
ax.barh(
    df["name"],
    df["code"],
    left=df["comment"],  # Offset is based on the 'comment' field used previously
    color="blue",
    edgecolor="black",
    label="Code count",
)

# And then 'empty' data placed last
ax.barh(
    df["name"],
    df["empty"],
    left=df["comment"] + df["code"],  # Building on top of the existing values
    color="gray",
    label="Empty",
)

ax.grid(True)
ax.legend(loc="lower right")
ax.set_xlabel("Line count")
comment_percent = df["comment"].sum() / df["code"].sum()
# Verbose title with some numerical statistics for a high-level overview of the project
ax.set_title(
    f"Line category breakdown, code total is {df['code'].sum()}, "
    + f"comment total is {df['comment'].sum()} ({comment_percent:4.3}%) "
    + f"empty {df['empty'].sum()}"
)
fig.savefig(args.outfile, bbox_inches="tight", dpi=300)
