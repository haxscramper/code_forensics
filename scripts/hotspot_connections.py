#!/usr/bin/env python

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sqlite3
import math
import igraph as ig
from cli_common import *

parser = init_parser()
args = parse_args_with_config(parser)

plt.rcParams["font.family"] = "consolas"
plt.rcParams["axes.facecolor"] = "white"

con = sqlite3.connect(args.database)
df = pd.read_sql_query(
    """
select rcommit, path as file_id, strings.text as path
from edited_files
inner join strings on strings.id = edited_files.path
""",
    con,
)


df = df[
    df.apply(
        lambda r: r.path.startswith("compiler") and r.path.endswith(".nim"), axis=1
    )
]

g = ig.Graph()
node_table = {}
gb = df.groupby("rcommit")

path_count = {}
path_ids = {}


def get_vertex(path: str):
    if path not in path_ids:
        path_ids[path] = g.vcount()
        g.add_vertices(1)

    return path_ids[path]


pair_list = {}
vertex_weight = {}

for group in gb.groups:
    commit = gb.get_group(group)
    for node1 in commit["path"]:
        v1 = get_vertex(node1)
        if v1 not in vertex_weight:
            vertex_weight[v1] = 0

        vertex_weight[v1] += 1
        for node2 in commit["path"]:
            v2 = get_vertex(node2)
            if v1 != v2:
                if not g.are_connected(v1, v1):
                    if v1 not in pair_list:
                        pair_list[v1] = {}

                    if v2 in pair_list[v1]:
                        pair_list[v1][v2] += 1

                    else:
                        pair_list[v1][v2] = 1

vertex_list = []
attr_list = []
for v1, v2 in pair_list.items():
    for k, v in v2.items():
        vertex_list.append((v1, k))
        attr_list.append(v)

for v, w in vertex_weight.items():
    g.vs[v]["weight"] = w

g.add_edges(vertex_list, attributes={"weight": attr_list})

g.delete_edges(g.es.select(lambda e: e["weight"] < 200))

ig.summary(g)
ig.plot(
    g,
    layout=g.layout(layout="auto"),
    target="/tmp/db.png",
    vertex_size=[5 * math.log(size) + 1 for size in g.vs["weight"]],
    bbox=(1200, 1200),
)

print(f"Generated layoyut")

# print(f"count: {g.ecount()}")
#     g.es[g.get_eid(v1, v2)]["weight"] = 1

# else:
#     g.vs[g.get_eid(v1, v2)]["weight"] += 1
