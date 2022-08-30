#!/usr/bin/env python

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sqlite3
import math
import igraph as ig
import cli_common as cc
import sys
from tqdm import tqdm

tqdm.pandas()


def parse_args(args=sys.argv[1:]):
    parser = cc.init_parser()
    parser.add_argument(
        "--mode",
        type=str,
        dest="mode",
        choices=["graph", "heatmap", "heatmap-fraction", "overwrite"],
        default="graph",
        help="Hotspot correlation analysis mode. 'heatmap' - correlation between the most edited files in absolute numbers, 'heatmap-fraction' - correlation between most edited files in relation to their total edits, 'overwrite' - most rewritten files",
    )

    parser.add_argument(
        "--top",
        type=int,
        dest="top",
        default=50,
        help="Top N files for the correlation heatmap. Applicable for the heatmap generation",
    )

    parser.add_argument(
        "--ordering-mode",
        type=str,
        dest="ordering_mode",
        default="self-edit",
        choices=["self-edit", "connections", "top-connection"],
        help="Odering mode for the top edited files. 'self-edit' will order by total number edits of the file, 'connections' will order by the total number of edits made with some other files. 'top-collection' will order by the maximum number of edits with other files.",
    )

    parser.add_argument(
        "--graph.min_correlation",
        type=int,
        dest="graph_min_correlation",
        default=100,
        help="Minimal number of time two files had to be edited together in order to be linked together in the graph",
    )

    return cc.parse_args_with_config(parser, args)


def get_groups(args):
    con = sqlite3.connect(args.database)
    resolver = cc.PathResolver(con)
    df = pd.read_sql_query(
        "select rcommit, edited_files.path as file_id from edited_files", con
    )

    df["path"] = df["file_id"].apply(lambda id: resolver.resolve_path(id))

    df = df[
        df.apply(
            # HACK expose proper configuration options for file
            # filtering
            lambda r: r.path.startswith("compiler")
            and r.path.endswith(".nim"),
            axis=1,
        )
    ]

    return (resolver, df.groupby("rcommit"))


def co_edit_stats(gb, g):
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

    return (pair_list, vertex_weight, path_ids)


def heatmap_correlation(args):
    (resolver, gb) = get_groups(args)
    g = ig.Graph()
    (pair_list, vertex_weight, path_ids) = co_edit_stats(gb, g)

    rev_ids = {}
    for k, v in path_ids.items():
        rev_ids[v] = k

    weight_map = {}

    omode = args.ordering_mode

    if omode == "self-edit":
        weight_map = vertex_weight

    elif omode in ["connections", "top-connection", "top-fraction"]:
        dedup_set = set()
        weight_map = {}
        for it1, key in pair_list.items():
            adjacent_edits = []
            for it2, value in pair_list[it1].items():
                if (
                    it1 != it2
                    and (it1, it2) not in dedup_set
                    and (it2, it1) not in dedup_set
                ):
                    dedup_set.add((it1, it2))
                    adjacent_edits.append(value)

            if omode == "connections":
                weight_map[it1] = sum(adjacent_edits)

            elif omode == "top-connection":
                weight_map[it1] = max(adjacent_edits) if adjacent_edits else 0

    count = pd.DataFrame(
        weight_map.items(), columns=["path_id", "count"]
    ).sort_values(["count"], ascending=False)

    edit = [
        resolver.resolve_id(id)
        for id in count.head(min(count["count"].count(), args.top))["path_id"]
    ]

    heatmap = np.zeros([len(edit), len(edit)])
    heatmap = heatmap.astype(int)

    for idx1, it1 in enumerate(edit):
        for idx2, it2 in enumerate(edit):
            if it1 in pair_list and it2 in pair_list[it1]:
                if args.mode == "heatmap-fraction":
                    heatmap[idx1][idx2] = int(
                        pair_list[it1][it2] / vertex_weight[it1] * 100
                    )

                else:
                    heatmap[idx1][idx2] = pair_list[it1][it2]

    fig, ax = plt.subplots(figsize=(12, 12))

    ax.imshow(heatmap)
    ax.set_yticks(
        np.arange(len(edit)),
        [
            "{} ({}{})".format(
                rev_ids[id],
                int(weight_map[id]),
                "%" if omode == "top-fraction" else "",
            )
            for id in edit
        ],
    )

    ax.set_xticks(
        np.arange(len(edit)),
        [rev_ids[id] for id in edit],
        rotation=45,
        ha="right",
        rotation_mode="anchor",
    )

    for i in range(len(edit)):
        for j in range(len(edit)):
            ax.text(j, i, heatmap[i, j], ha="center", va="center", color="w")

    descriptions = [
        ["edited", "edit count"],
        ["connected", "connection count"],
        ["connected", "maximum common edit count"],
    ]

    idx = ["self-edit", "connections", "top-connection", "top-fraction"].index(
        omode
    )

    ax.set_title(
        args.title
        or "Edit {} of the top {} most {}, ignoring self-edit, showing {}".format(
            "correlation"
            if args.mode == "heatmap"
            else "correlation fraction",
            args.top,
            descriptions[idx][0],
            descriptions[idx][1],
        )
    )

    fig.savefig(args.outfile, dpi=300, bbox_inches="tight")


def graph_correlation(args):
    (resolver, gb) = get_groups(args)
    g = ig.Graph()
    (pair_list, vertex_weight, path_ids) = co_edit_stats(gb, g)

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

    g.vs["inweight"] = [
        sum([g.es[e]["weight"] for e in g.incident(v)]) for v in g.vs
    ]

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
    g.es["penwidth"] = [
        int(math.log(size - base + 1) + 1) for size in g.es["weight"]
    ]
    g.vs["penwidth"] = [
        max([g.es[e]["penwidth"] for e in g.incident(v)]) for v in g.vs
    ]
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


def overwrite_breakdown(args):
    con = sqlite3.connect(args.database)

    resolver = cc.PathResolver(con)
    df = pd.read_sql_query(
        "select rcommit, added, removed, path as file_id from edited_files",
        con,
    )

    df["file_id"] = df["file_id"].apply(lambda id: resolver.resolve_id(id))

    per_file = {}
    gb = df.groupby("file_id")
    for gr in gb.groups:
        df_file = gb.get_group(gr)
        per_file[gr] = (df_file["added"].sum(), df_file["removed"].sum())

    df = pd.DataFrame(
        [(id, add, remove) for (id, (add, remove)) in per_file.items()],
        columns=["file_id", "added", "removed"],
    )

    df["path"] = df["file_id"].apply(lambda id: resolver.resolve_path(id))
    df = df[df.apply(lambda r: r["path"].startswith("compiler"), axis=1)]
    max_added = int(math.log(df["added"].max(), 10) + 1)
    max_removed = int(math.log(df["removed"].max(), 10) + 1)

    df["edits"] = df.apply(
        lambda r: "+{:>{}}/-{:>{}}".format(
            r["added"], max_added, r["removed"], max_removed
        ),
        axis=1,
    )
    max_name = df["path"].apply(lambda r: len(r)).max()
    max_edit = df["edits"].apply(lambda r: len(r)).max()

    df["name"] = df.apply(
        lambda r: f"{r.path:-<{max_name}}{r.edits:->{max_edit}}", axis=1
    )

    df["total"] = df["added"] + df["removed"]
    df = df.sort_values("total")
    size = min(len(df.index), args.top)
    df = df.tail(size)

    fig, ax = plt.subplots(figsize=(12, 34))

    ax.barh(
        df["name"],
        df["added"],
        color="green",
        edgecolor="black",
        label="Added lines",
    )
    ax.barh(
        df["name"],
        df["removed"],
        left=df["added"],
        color="red",
        edgecolor="black",
        label="Removed lines",
    )

    ax.grid(True)
    ax.legend(loc="lower right")
    ax.set_title(
        args.title or "Total number of added and removed lines, per file"
    )
    fig.savefig(args.outfile, bbox_inches="tight", dpi=300)


def impl(args):
    if args.mode == "graph":
        graph_correlation(args)

    elif args.mode in ["heatmap", "heatmap-fraction"]:
        heatmap_correlation(args)

    elif args.mode == "overwrite":
        overwrite_breakdown(args)


if __name__ == "__main__":
    plt.rcParams["font.family"] = "consolas"
    if len(sys.argv) == 1:
        impl(parse_args(["/tmp/Nim.sqlite", "/tmp/Nim.dot", "--mode=graph"]))
    else:
        impl(parse_args())
