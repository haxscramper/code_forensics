#!/usr/bin/env python

from cli_common import *
import matplotlib.pyplot as plt
import re
import pandas as pd
import sqlite3

parser = init_parser()
add_rename_args(parser)
add_ignore_args(parser)
parser.add_argument(
    "--mode",
    dest="mode",
    type=str,
    default="per-user",
    choices=["per-user", "over-time"],
    help="Wich percentile plot to produce",
)
args = parser.parse_args()

df = pd.read_sql_query(
    """
select name, hash, time, message
from rcommit
inner join author on author.id == rcommit.author;
    """,
    sqlite3.connect(args.database),
)


def clearmsg(msg: str) -> str:
    result = msg
    for pat in [r"\(#\d+\)", r"\[backport\]", r"fixes:? *#\d+"]:
        result = re.sub(pat, "", result, flags=re.IGNORECASE)

    return result


df = df.sort_values(by=["time"])
df["name"] = df["name"].apply(lambda name: remap_name(args, name))
df["time"] = pd.to_datetime(df["time"], unit="s")
df["len"] = df["message"].apply(lambda msg: len(msg))
df["clearlen"] = df["message"].apply(lambda msg: len(clearmsg(msg)))
df = df.drop("message", axis=1)
df = df.loc[
    lambda row: row["name"].apply(lambda name: name not in set(args.ignore or []))
]

cap_max = df["len"].quantile(0.999)
df = df[df["len"] < cap_max]
fig, ax = plt.subplots(figsize=(16, 16))


if args.mode == "per-user":
    df = df[["name", "time", "len", "clearlen"]]
    df = df.set_index("time")
    # df["len"] = df["len"].ewm(span=60).mean()
    gb = df.groupby("name")
    gb = (
        gb.size()
        .to_frame("count")
        .join(gb["len"].agg(mean=np.mean))
        .join(
            gb["len"].agg(min=lambda x: x.loc[lambda it: x.quantile(0.10) < it].min())
        )
        .join(
            gb["len"].agg(max=lambda x: x.loc[lambda it: it < x.quantile(0.90)].max())
        )
        .join(gb["clearlen"].agg(clearlen_mean=np.mean))
        .sort_values(by="count")
        .reset_index()
    )

    gb["mix"] = gb.apply(lambda row: row["mean"] * row["count"], axis=1)

    gb = gb[gb["count"].quantile(0.90) < gb["count"]]
    print(gb)

    gb = gb.sort_values(by="mean")

    gb["labels"] = gb.apply(
        lambda row: f"{row['name']} ({row['count']}) "
        + f"~ {row['mean']:5.1f}/{row['min']}/{row['max']}",
        axis=1,
    )

    ax.errorbar(
        gb["mean"],
        gb["labels"],
        xerr=(gb["mean"] - gb["min"], gb["max"] - gb["mean"]),
        fmt="b",
        ecolor="blue",
        label="average message",
    )

    ax.plot(gb["clearlen_mean"], gb["labels"], "r", label="without 'fixes #' noise")

    ax.set_title(
        "average commit message length per contributor "
        + "(.999th commit length percentile)"
    )
    ax.set_ylabel("author name, total commit count + " + "mean/min/max length")
    ax.set_xlabel("message character count")
    ax.legend(loc="lower right")

else:
    df["len"] = df["len"].ewm(span=40).mean()
    df.plot(x="time", y="len", ax=ax)
    ax.set_ylabel("Character count")
    ax.set_title(
        "Number of characters in the commit message, 99th percentile, rolling 50 average"
    )

ax.grid(True)
fig.set_dpi(300)
fig.savefig(args.outfile, bbox_inches="tight")
