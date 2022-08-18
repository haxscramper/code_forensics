from forensics import config
import datetime
import sys
import argparse

# Code filter script can accept CLI arguments - main execution program can pass them via `--filter-arg=<argument>` (the option can be repeated)
parser = argparse.ArgumentParser(description="Code filter script configuration")

# Number of samples that should be taken per commit
parser.add_argument(
    "--per-year",
    dest="per_year",
    type=int,
    default=1,
    help="Number of samples per year",
)


parser.add_argument(
    "--target",
    dest="target",
    type=str,
    default="nim",
    help="Which of the predefined predicate configurations to use",
)


args = parser.parse_args()

# Configuration object can also access logging functionality
config.log_info(f"Number of samples per year: {args.per_year}")


# We are only interested in the code in the main compiler directory, and ignoring everything else
def path_predicate(path: str) -> bool:
    if args.target in ["nim", "nimskull"]:
        if path.endswith(".nim"):
            return path.startswith("compiler") or path.startswith("rod")

        elif path.endswith(".rod"):
            return path.startswith("nim")

        else:
            return False

    else:
        return True


# You can use module-level variables to have some persistent data stored between predicate runs
visited_years = set()


def sample_period_mapping(date) -> bool:
    shift = date.month // int(12 / args.per_year)
    result = date.year * args.per_year + shift
    return result


def sample_predicate(date, author: str, oid: str) -> bool:
    # Trim earlier years for testing convenience - this script is used to
    # run on the nim/nimskull repository, which was originally transpiled
    # from the pascal code, and there are some weird glitches in the
    # output beacuse of that.
    if date.year < 2011:
        return False

    period = sample_period_mapping(date)

    if period in visited_years:
        return False

    else:
        visited_years.add(period)
        return True


def commit_period_mapping(date) -> bool:
    return date.year


def classify_line(line: str) -> int:
    if line.startswith(" "):
        return 1
    else:
        return 0


def post_analyze():
    config.log_info("Post-analysis hook")


config.set_path_predicate(path_predicate)
config.set_sample_predicate(sample_predicate)
config.set_commit_period_mapping(commit_period_mapping)
config.set_sample_period_mapping(sample_period_mapping)
config.set_line_classifier(classify_line)
config.set_post_analyze(post_analyze)
