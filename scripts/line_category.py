#!/usr/bin/env python

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

from cli_common import *

parser = init_parser()
args = parser.parse_args()

con = sqlite3.connect(args.database)
cur = con.cursor()


cur.execute("drop view if exists commit_file_lines;")
cur.execute(open(Path(__file__).parent / "line_category.sql").read())


def content_category(content: str) -> int:
    if "##" in content:
        return 1

    else:
        return 0


content_map = {}

for (id, text) in cur.execute("select id, text from strings;"):
    content_map[id] = content_category(text)

df = pd.read_sql_query(
    """
SELECT cfl.commit_time,
       cfl.file_path,
       line.content
  FROM commit_file_lines AS cfl
 INNER JOIN LINE
    ON cfl.line_id == line.id;
""",
    con,
)

time = df["commit_time"].max()

df = df[df["commit_time"] == time]
df["category"] = df["content"].apply(lambda content: content_map[content])

df = (
    df.groupby(["file_path"])
    .agg(
        comment=("category", lambda x: x.loc[x == 1].count()),
        code=("category", lambda x: x.loc[x == 0].count()),
    )
    .reset_index()
)

df["total"] = df["code"] + df["comment"]
df = df.sort_values("total", ascending=False)
print(df)
df.to_csv("/tmp/saved.csv")

print(df)

fig, ax = plt.subplots(figsize=(16, 34))
ax.invert_yaxis()
df["name"] = df.apply(lambda row: f"{row['file_path']} ({row['total']})", axis=1)
ax.barh(df["name"], df["comment"], color="green", edgecolor="black", label="Code count")

ax.barh(
    df["name"],
    df["code"],
    left=df["comment"],
    color="blue",
    edgecolor="black",
    label="Code count",
)

ax.grid(True)
# ax.set_yticks(ax.get_yticks())
# ax.set_yticklabels(
#     df.apply(lambda row: f"{row['file_path']} ({row['total']})", axis=1), ha="left"
# )
ax.legend(loc="lower right")
ax.set_xlabel("Line count")
ax.set_title("Line category breakdown")
fig.savefig(args.outfile, bbox_inches="tight", dpi=300)
