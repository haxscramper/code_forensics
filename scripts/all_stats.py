#!/usr/bin/env python

import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "consolas"


from cli_common import *
import line_category
import code_authorship
import hotspot_connections
import commit_message_length
import top_comitters
import author_ridgeline
import yaml
import sys

parser = argparse.ArgumentParser(description="Process some integers.")
parser.add_argument("database", type=str, help="Input database file")
parser.add_argument("outdir", type=str, help="Output analytics image directory")
parser.add_argument(
    "--config",
    dest="config",
    type=str,
    help="Extra toplevel configuration",
    default=None,
)

parser.add_argument(
    "--subconfig",
    dest="subconfig",
    type=str,
    help="Sub-script configuration file that will be passed to each analytics",
    default=None,
)

args = parser.parse_args()

modules = [
    "top_comitters",
    "hotspot_connections",
    "line_category",
    "code_authorship",
    # FIXME commit message length is WIP - need to handle negative xerr
    # ranges that mmight occur sometimes.
    #
    # "commit_message_length",
    # "author_ridgeline",
]

sub_args = {}

if args.config:
    conf = yaml.load(open(args.config, "r").read(), Loader=yaml.Loader)
    for name in modules:
        database = args.database
        outfile = f"{args.outdir}/{name}.png"
        extra = []
        if args.subconfig:
            extra.append(f"--config={args.subconfig}")

        if name in conf:
            for prop, value in conf[name].items():
                if prop == "outfile":
                    outfile = value

                elif prop == "database":
                    database = value

                else:
                    extra.append(f"--{prop}={value}")

        sub_args[name] = [database, outfile] + extra

for name in modules:
    mod = globals()[name]
    final_args = sub_args[name]
    print(f"./scripts/{name}.py", *final_args)
    args = mod.parse_args(final_args)
    mod.impl(args)

print("all done")
