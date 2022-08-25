#!/usr/bin/env python

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sqlite3
import math
import igraph as ig
from cli_common import *

parser = init_parser()
parser.add_argument(
    "--mode",
    type=str,
    dest="mode",
    choices=["graph", "correlation"],
    default="graph",
    help="Hotspot correlation analysis mode",
)

parser.add_argument(
    "--graph.min_correlation",
    type=int,
    dest="graph_min_correlation",
    default=200,
    help="Minimal number of time two files had to be edited together in order to be linked together in the graph",
)

args = parse_args_with_config(parser)

plt.rcParams["font.family"] = "consolas"
plt.rcParams["axes.facecolor"] = "white"

con = sqlite3.connect(args.database)


def graph_correlation():
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
    dedup_set = set()
    for v1, v2 in pair_list.items():
        for k, v in v2.items():
            if (v1, k) not in dedup_set or (k, v1) not in dedup_set:
                dedup_set.add((v1, k))
                dedup_set.add((k, v1))
                vertex_list.append((v1, k))
                attr_list.append(v)

    for v, w in vertex_weight.items():
        g.vs[v]["weight"] = w

    for path, v in path_ids.items():
        g.vs[v]["path"] = path

    g.add_edges(vertex_list, attributes={"weight": attr_list})

    g.vs["inweight"] = [sum([g.es[e]["weight"] for e in g.incident(v)]) for v in g.vs]

    base = args.graph_min_correlation
    g.delete_edges(g.es.select(lambda e: e["weight"] < base))
    g.delete_vertices(g.vs.select(lambda v: v.degree() == 0))
    g.vs["inweight_clean"] = [
        sum([g.es[e]["weight"] for e in g.incident(v)]) for v in g.vs
    ]
    g.vs["label"] = [
        "{}\nedit: {}, adj: {}, adj(all): {}".format(
            v["path"], v["weight"], v["inweight_clean"], v["inweight"]
        )
        for v in g.vs
    ]
    g.es["label"] = [str(size) for size in g.es["weight"]]
    g.es["penwidth"] = [int(math.log(size - base + 1) + 1) for size in g.es["weight"]]
    g.vs["penwidth"] = [max([g.es[e]["penwidth"] for e in g.incident(v)]) for v in g.vs]
    g.vs["size"] = [5 * math.log(size) + 1 for size in g.vs["weight"]]

    if args.outfile.endswith(".dot"):
        dot = args.outfile

        g.write(dot)
        text = ""

        with open(dot, "r") as file:
            text = file.read()

        text = text.replace(
            "graph {",
            f"""
graph {{
     fontname="consolas";
     label="Edited together {base} times or more";
     node[shape=box, fontname="consolas",margin="0.5"];
     edge[fontname="consolas"];
     graph[splines=polyline];
     rankdir=LR;
        """,
        )

        with open(dot, "w") as file:
            file.write(text)

    else:
        g.write(args.outfile)


if args.mode == "graph":
    graph_correlation()
