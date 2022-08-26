import argparse
import numpy as np
import matplotlib.pyplot as plt
import sys
import functools
from typing import *

from datetime import datetime
from matplotlib.dates import YearLocator, MonthLocator, DateFormatter
from matplotlib.dates import date2num


def format_x_dates(it):
    # set x-ticks in date
    # see: http://matplotlib.sourceforge.net/examples/api/date_demo.html
    it.xaxis.set_major_locator(YearLocator())
    it.xaxis.set_major_formatter(DateFormatter("%Y"))
    it.xaxis.set_minor_locator(MonthLocator())
    # format the coords message box
    it.format_xdata = DateFormatter("%Y-%m-%d")


def from_timestamps(timestamps: List[int]):
    result = []
    for time in timestamps:
        result.append(date2num(datetime.utcfromtimestamp(time)))

    return result


def align_yaxis(axes):
    y_lims = np.array([ax.get_ylim() for ax in axes])

    # force 0 to appear on all axes, comment if don't need
    y_lims[:, 0] = y_lims[:, 0].clip(None, 0)
    y_lims[:, 1] = y_lims[:, 1].clip(0, None)

    # normalize all axes
    y_mags = (y_lims[:, 1] - y_lims[:, 0]).reshape(len(y_lims), 1)
    y_lims_normalized = y_lims / y_mags

    # find combined range
    y_new_lims_normalized = np.array(
        [np.min(y_lims_normalized), np.max(y_lims_normalized)]
    )

    # denormalize combined range to get new axes
    new_lims = y_new_lims_normalized * y_mags
    for i, ax in enumerate(axes):
        ax.set_ylim(new_lims[i])


def init_parser(with_common=True):
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("database", type=str, help="Input database file")
    parser.add_argument("outfile", type=str, help="Output plot image")
    if with_common:
        add_rename_args(parser)
        add_ignore_args(parser)
        add_config_args(parser)
        add_title_args(parser, None)

    return parser


import sqlite3


def open_db(args):
    con = sqlite3.connect(args.database)
    cur = con.cursor()
    return cur


def add_rename_args(parser):
    parser.add_argument(
        "--rename",
        dest="rename",
        type=str,
        action="append",
        help="Name=Other pair for handling users with multiple names",
    )


def add_ignore_args(parser):
    parser.add_argument(
        "--ignore",
        dest="ignore",
        type=str,
        action="append",
        help="List of users to ignore",
    )


def remap_name(args, name: str) -> str:
    rename = [] if not args.rename else args.rename
    remap = [(it[0], it[1]) for it in [pair.split("=") for pair in rename]]
    for (old, new) in remap:
        if name == old:
            return new

    return name


def add_config_args(parser):
    parser.add_argument(
        "--config",
        action="append",
        type=str,
        dest="config",
        default=None,
        help="One or more configuration files to read options from",
    )


def add_title_args(parser, default: str):
    parser.add_argument(
        "--title", type=str, dest="title", default=default, help="Resulting plot title"
    )


def read_configs(parser, args, base_args=sys.argv[1:]):
    if args.config:
        options = []
        for path in args.config:
            with open(path, "r") as file:
                for line in file.read().split("\n"):
                    line = line.strip()
                    if not (line.startswith("#") or len(line) == 0):
                        split = line.split("=")
                        if 1 < len(split):
                            options.append(
                                split[0] + "=" + "=".join(split[1:]).strip('"')
                            )
                        else:
                            options.append(split[0])

        new = base_args + options
        new_args = parser.parse_args(new)
        return new_args

    else:
        return args


def parse_args_with_config(parser, args_list=sys.argv[1:]):
    args = parser.parse_args(args_list)
    return read_configs(parser, args, args_list)


class PathResolver:
    def __init__(self, con):
        self.path_id_map = {}
        for (id, path) in con.execute("select path_id, path from file_path_with_dir"):
            self.path_id_map[id] = path

        self.rename_forward = {}
        self.rename_backward = {}

        for (old, new) in con.execute("select old_path, new_path from renamed"):
            if old not in self.rename_forward:
                self.rename_forward[old] = []
            if new not in self.rename_backward:
                self.rename_backward[new] = []

            self.rename_forward[old].append(new)
            self.rename_backward[new].append(old)

    @functools.cache
    def resolve_id(self, id, forward: bool = True):
        result = id
        remap = self.rename_forward if forward else self.rename_backward
        already_visited = set()
        while result in remap:
            found = False
            for option in remap[result]:
                if option not in already_visited:
                    found = True
                    result = option
                    already_visited.add(option)

            if not found:
                break

        return result

    def resolve_path(self, id, forward: bool = True):
        return self.path_id_map[self.resolve_id(id, forward)]
