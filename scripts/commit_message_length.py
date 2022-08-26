#!/usr/bin/env python

from cli_common import *
import matplotlib.pyplot as plt
import re
import math
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
import sys


def parse_args(args=sys.argv[1:]):
    parser = init_parser()
    add_title_args(parser, None)

    parser.add_argument(
        "--mode",
        dest="mode",
        type=str,
        default="per-user",
        choices=["per-user", "over-time"],
        help="Wich percentile plot to produce",
    )

    parser.add_argument(
        "--top-contributors",
        dest="top_contributors",
        type=float,
        default=0.10,
        help="Top percentile of the controibutors to plot",
    )

    return parse_args_with_config(parser, args)


# Remove automation boilerplate text from the message
def clearmsg(msg: str) -> str:
    result = msg
    for pat in [r"\(#\d+\)", r"\[backport\]", r"fixes:? *#\d+"]:
        result = re.sub(pat, "", result, flags=re.IGNORECASE)

    return result


def impl(args):
    # No external SQL query script - input data is very simple in this case
    df = pd.read_sql_query(
        """
    select name, hash, time, message
    from rcommit
    inner join author on author.id == rcommit.author;
        """,
        sqlite3.connect(args.database),
    )

    df = df.sort_values(by=["time"])
    # Apply rename configuration provided from the command line
    df["name"] = df["name"].apply(lambda name: remap_name(args, name))
    # Parse datetime values into the pandas content - specify unit="s" to select input source
    df["time"] = pd.to_datetime(df["time"], unit="s")
    # Calculate legths of original messages
    df["len"] = df["message"].apply(lambda msg: len(msg))
    # And length of the cleaned message versions
    df["clearlen"] = df["message"].apply(lambda msg: len(clearmsg(msg)))
    # After that this column is no longer needed
    df = df.drop("message", axis=1)
    # Drop ignored names from the list as well
    df = df.loc[
        lambda row: row["name"].apply(lambda name: name not in set(args.ignore or []))
    ]

    # Only process commits that are withing 0-0.999 percentile range of the
    # input. Usually outlier commits are rater large - squashes, octopus merges
    # and so on.
    df = df[df["len"] < df["len"].quantile(0.999)]
    # Create base figure and subplot
    fig, ax = plt.subplots(figsize=(16, 16))

    if args.mode == "per-user":
        # Calculate per-user average statistics of the commmit messages

        # Drop everything but the necessary column values
        df = df[["name", "time", "len", "clearlen"]]
        df = df.set_index("time")
        gb = df.groupby("name")
        gb = (
            # Create new dataframe with information about each group size and then join additional aggregate columns to it incrementally
            gb.size()
            .to_frame("count")  # Count each grop's size
            .join(gb["len"].agg(mean=np.mean))  # Average it's commit message lenght
            .join(  # Count minimum message, using 10-90% percentile range
                gb["len"].agg(
                    min=lambda x: x.loc[lambda it: x.quantile(0.10) < it].min()
                )
            )
            .join(  # Count maximum message using the same percentile range
                gb["len"].agg(
                    max=lambda x: x.loc[lambda it: it < x.quantile(0.90)].max()
                )
            )
            .join(
                gb["clearlen"].agg(clearlen_mean=np.mean)
            )  # Add information about clered message length
            .sort_values(by="count")  # Sort by number of commits
            .reset_index()  # Reset index so I can directly access `["count"]` and other columns that were added as indices in the grouping
        )

        # Number of characters written in the commit message logs
        gb["mix"] = gb.apply(lambda row: row["mean"] * row["count"], axis=1)

        # Filter out everything aside from Nth top percentile (supplied via command line)
        gb = gb[gb["count"].quantile(1 - args.top_contributors) < gb["count"]]

        # Arrange values by average length of the message
        gb = gb.sort_values(by="mean")

        # Add verbose labels to the text output
        gb["labels"] = gb.apply(
            lambda row: f"{row['name']} ({row['count']}) "
            + f"~ {row['mean']:5.1f}/{int(row['min'])}/{int(row['max'])}",
            axis=1,
        )

        # Plot aveage commit message lenght. Use min/max range as an error band in the display
        ax.errorbar(
            gb["mean"],
            gb["labels"],  # Use names as y values for the sake of readability
            xerr=(gb["mean"] - gb["min"], gb["max"] - gb["mean"]),
            fmt="b",
            ecolor="blue",
            label="average message",
        )

        ax.plot(gb["clearlen_mean"], gb["labels"], "r", label="without 'fixes #' noise")

        ax.set_title(
            args.title
            or (
                "average commit message length per contributor "
                + "(.999th commit length percentile)"
            )
        )
        ax.set_ylabel("author name, total commit count + " + "mean/min/max length")
        ax.set_xlabel("message character count")
        ax.legend(loc="lower right")

    else:
        df["len"] = df["len"].ewm(span=40).mean()
        df.plot(x="time", y="len", ax=ax)
        ax.set_ylabel("Character count")
        ax.set_title(
            args.title
            or "Number of characters in the commit message, 99th percentile, rolling 50 average"
        )

    ax.grid(True)
    fig.set_dpi(300)
    fig.savefig(args.outfile, bbox_inches="tight")


if __name__ == "__main__":
    impl(parse_args())
