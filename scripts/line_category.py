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
    if "#" in content:
        return 1

    else:
        return 0


content_map = {}

for (id, text) in cur.execute("select id, text from strings;"):
    content_map[id] = content_category(text)

df = pd.read_sql_query(
    """
SELECT cfl.commit_id,
       cfl.file_path,
       cfl.line_id,
       line.content
  FROM commit_file_lines AS cfl
 INNER JOIN LINE
    ON cfl.line_id == line.id;
""",
    con,
)
df["category"] = df["content"].apply(lambda content: content_map[content])
print(df)
gb = df.groupby(["commit_id", "file_path", "category"])

df = gb.size().to_frame("lines")

print(df)
