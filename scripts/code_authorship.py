#!/usr/bin/env python

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import cli_common as cli
import sys


def parse_args(args=sys.argv[1:]):
    parser = cli.init_parser()
    parser.add_argument(
        "--top",
        dest="top",
        default=15,
        type=int,
        help="How many committers from the top to plot",
    )

    return cli.parse_args_with_config(parser, args)


def impl(args):
    cur = cli.open_db(args)

    total_writers = {}
    all_periods = set()
    author_period_map = {}

    for row in cur.execute(
        open(Path(__file__).parent / "code_authorship.sql").read()
    ):
        (author, period, line_count) = row
        all_periods.add(period)
        name = cli.remap_name(args, author)
        if name not in total_writers:
            total_writers[name] = 0

        if name not in author_period_map:
            author_period_map[name] = {}

        total_writers[name] += line_count
        if period not in author_period_map[name]:
            author_period_map[name][period] = 0

        author_period_map[name][period] += line_count

    # pprint.pprint(total_writers)
    authors_ordered = sorted(
        total_writers.items(), key=lambda it: it[1], reverse=True  #
    )
    other_authors = {}

    per_period = {period: 0 for period in all_periods}
    for author, per_map in author_period_map.items():
        for period, count in per_map.items():
            per_period[period] += count

    top_n = args.top

    for author, count in authors_ordered[(top_n) - 1 : -1]:
        for period in author_period_map[author]:
            if period not in other_authors:
                other_authors[period] = 0

            other_authors[period] += author_period_map[author][period]

        del author_period_map[author]

    author_period_map["other"] = other_authors
    total_writers["other"] = sum([count for _, count in other_authors.items()])

    authors_ordered = sorted(
        total_writers.items(), key=lambda it: it[1], reverse=True
    )

    for author_idx, (author, count) in enumerate(authors_ordered):
        if author in author_period_map:
            for period in sorted(all_periods):
                if period not in author_period_map[author]:
                    author_period_map[author][period] = 0

    full_count = sum([count for _, count in total_writers.items()])

    if full_count == 0:
        print(
            "no code was registered during the DB analysis "
            "- compile the database with --analytics=BlameBurndown enabled"
        )
        exit(1)

    global_percentage = {  #
        name: 100 * (count / full_count)
        for name, count in total_writers.items()
    }

    sample_count: int = len(all_periods)
    author_count: int = len(author_period_map)

    data = np.zeros([author_count, sample_count]).astype(int)
    indexed_authors = []

    authors = [name for (name, _) in authors_ordered[:top_n]]

    for author_idx, author in enumerate(authors):
        indexed_authors.append(author)
        for period_idx, period in enumerate(
            sorted(author_period_map[author].keys())  #
        ):
            lines = author_period_map[author][period]
            data[author_idx][period_idx] = lines

    offset = np.zeros(sample_count)
    index = list(sorted(all_periods))
    colors = plt.cm.rainbow(np.linspace(0, 0.8, author_count))

    plt.figure(figsize=(10, 12), dpi=300, constrained_layout=True)

    for author_idx, samples in enumerate(data):
        if top_n - 1 < author_idx:
            break
        name = indexed_authors[author_idx]
        plt.bar(
            index,
            samples,
            width=1.0,
            bottom=offset,
            color=colors[author_idx],
            edgecolor="black",
            label=f"{name} ({global_percentage[name]:4.2f}%)",
        )

        offset = offset + samples

    plt.legend(loc="upper left")
    plt.savefig(args.outfile, bbox_inches="tight")


if __name__ == "__main__":
    plt.rcParams["font.family"] = "consolas"
    impl(parse_args())
