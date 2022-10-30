#!/usr/bin/env python

from matplotlib import rcParams

rcParams["font.family"] = "consolas"

from pathlib import Path
import argparse


from copy import deepcopy
import sqlite3
import pprint
import itertools
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

parser = argparse.ArgumentParser(description="Process some integers.")

# Basic CLI handling for the script - to avoid hardcoding parameters
parser.add_argument("database", type=str, help="Input database file")
parser.add_argument("outfile", type=str, help="Output plot image")
parser.add_argument(
    "--per-year",
    dest="per_year",
    type=int,
    default=1,
    help="Number of samples per year",
)

parser.add_argument(
    "-f",
    "--fake-sample",
    nargs="+",
    help="Additional sample IDs that should be displayed on the plot as empty locations",
    dest="fake_samples",
    default=[],
    type=int,
)

args = parser.parse_args()
# Allow different number of commit samples per year
multi = args.per_year

con = sqlite3.connect(args.database)
cur = con.cursor()

# Store `[commit][change] -> count` mapping
samples_table = {}

# Deduplicated list of all change periods - assigned numbers might be
# spaced unevenly, have gaps etc. (one possible example is mapping
# `<year><month>` with zero-padding to six digits). Or some periods had no
# activity at all.
all_change_periods = set()


# Map commit period to the hash name
hash_table = {}

# Move main SQL selector script out of string literal into a separate file
for row in cur.execute(open(Path(__file__).parent / "table_per_period.sql").read()):
    commit = row[0]
    change = row[1]
    count = row[2]
    hash_table[f"{commit}"] = row[3]
    if commit not in samples_table:
        samples_table[commit] = {}

    all_change_periods.add(change)
    samples_table[commit][change] = count

for fake in args.fake_samples:
    samples_table[fake] = {}

sample_keys = list(sorted(samples_table.keys()))

# Fill in any missing data for the commit table with zeroes, unless it is a
# gap filler. If it is one, use information about the previous sample
for sample_idx, sample in enumerate(sample_keys):
    for change in sorted(all_change_periods):
        if change not in samples_table[sample]:
            if sample in args.fake_samples:
                # HACK can be unreliable for longer gaps at the start.
                # Right now it is designed to fill sections that were
                # caused by the unfinished year quarter - so only trailing
                # gaps.
                samples_table[sample][change] = samples_table[
                    sample_keys[sample_idx - 1]
                ][change]

            else:
                samples_table[sample][change] = 0


# Number of known change periods - can be completely different from the
# number of sampled commits
change_periods_num: int = len(all_change_periods)
# Number
commit_samples_num: int = len(samples_table)
# Change matrix
data = np.zeros([change_periods_num, commit_samples_num]).astype(int)

for commit_idx, commit in enumerate(sorted(samples_table.keys())):
    for change_idx, change in enumerate(sorted(samples_table[commit].keys())):
        lines = samples_table[commit][change]
        data[change_idx][commit_idx] = lines


def name_period(period: int) -> str:
    result = f"{period // multi} Q{period % multi + 1}"
    return result


# Sorted indices of the change periods
change_periods = [f"{change}" for change in sorted(all_change_periods)]
# Sorted indices of the commit samples
commit_samples = [f"{name_period(commit)}" for commit in sorted(samples_table.keys())]

name_w: int = max([len(name) for name in commit_samples]) + 1

# Print the analysis table directly
print(
    f"{'':>{name_w}} {'period':<{name_w}}",
    "".join([f"{count:<{name_w}}" for count in commit_samples]),
    sep="",
)

for idx, commit in enumerate(data):
    print(
        f"{idx:>{name_w}} {change_periods[idx]:<{name_w}}",
        "".join([f"{count:<{name_w}}" for count in commit]),
        sep="",
    )

# rainbow sequence of colors for each commit period - older periods will have a 'colder' color associated withtehm
colors = plt.cm.rainbow(np.linspace(0, 0.8, len(change_periods)))
# Generate range of indices for each sample point
index = np.arange(len(commit_samples))

# Create fixed-layout figure with given size
fig = plt.figure(figsize=(10, 12), constrained_layout=True)
# Two subplots - bar and the table
spec = gridspec.GridSpec(ncols=1, nrows=2, figure=fig)
# Stacked bar plot representation of the data
barplot = fig.add_subplot(spec[0, 0])
# Plot with numeric data that mirrors the barplot
change_table = fig.add_subplot(spec[1, 0])
barplot.set_ylabel("SLOC total")
# Tight fit of thee bar plot in order to precisely align it with the table
# change_periods below
barplot.margins(x=0)
# Initialize the vertical-offset for the stacked bar chart.
y_offset = np.zeros(len(commit_samples))


barplot.set_xticks(
    index,
    [f"{int(s/multi)} {(s % multi) + 1}/{multi}" for s in sorted(samples_table.keys())],
    rotation=90,
)

for commit_idx, samples in enumerate(data):
    # Create single layer of bar plot
    barplot.bar(
        index,  # Indices for each sample point
        samples,  # New sample information
        width=1.0,  # Full width, otherwise bars will be misalingned with
                    # table change_periods
        bottom=y_offset,  # baseline for bars
        color=colors[commit_idx],  # Each comit period has it's own unique color
        edgecolor="black",  # Distinct borders in case there are many periods
    )
    # Bars are stacked on each other
    y_offset = y_offset + samples

# Plot bars and create text labels for the table
cell_text = []
cell_colours = []  # 2D list of the table colors (gradients)
for commit_idx, samples in enumerate(data):
    res_colors = []
    count_max = samples.max()
    row_text = []
    for entry_idx, entry in enumerate(samples):
        row_text.append(f"{int(entry)}")

        if entry == 0:
            res_colors.append("white")

        else:
            # Interpolate color for changes in the current code by origin
            avg = entry / count_max
            color = deepcopy(colors[commit_idx])
            color[0] = (color[0] - 1.0) * avg + 1.0
            color[1] = (color[1] - 1.0) * avg + 1.0
            color[2] = (color[2] - 1.0) * avg + 1.0
            res_colors.append(color)

    cell_colours.append(res_colors)
    cell_text.append(row_text)

# Table plot does not need any axis information
change_table.axis("off")
change_table.axis("tight")


def filter_samples(samples):
    return samples[::-1][::multi][::-1]


assert len(commit_samples) == len(filter_samples(commit_samples)) * multi

table = change_table.table(
    cellText=[filter_samples(it) for it in cell_text],
    rowLabels=change_periods,
    cellColours=[filter_samples(it) for it in cell_colours],
    rowColours=colors,
    colLabels=filter_samples(commit_samples),
    loc="top",
)


# Create secondary table with total analysis
change_table.table(
    cellText=[filter_samples([str(it) for it in data.sum(axis=0)])],
    rowLabels=["Total"],
    loc="bottom",
)

# Remove any extraneous annotation on the main generated table
change_table.set_yticks([])
change_table.set_xticks([])

plt.savefig(args.outfile, bbox_inches="tight")
