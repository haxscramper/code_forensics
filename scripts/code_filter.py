from forensics import config
import datetime

# Configuration object can also access logging functionality
config.log_info("PY LOG: test from the user code")
config.log_error("PY_ERR")
config.log_warning("PY WARN")


# We are only interested in the code in the main compiler directory, and ignoring everything else
def path_predicate(path: str) -> bool:
    if path.endswith(".nim"):
        return path.startswith("compiler") or path.startswith("rod")

    elif path.endswith(".rod"):
        return path.startswith("nim")

    else:
        return False


# You can use module-level variables to have some persistent data stored between predicate runs
visited_years = set()


def sample_predicate(date, author, oid) -> bool:
    # Trim earlier years for testing convenience - this script is used to
    # run on the nim/nimskull repository, which was originally transpiled
    # from the pascal code, and there are some weird glitches in the
    # output beacuse of that.
    if date.year < 2010:
        return False

    if date.year in visited_years:
        return False

    else:
        visited_years.add(date.year)
        return True


def period_mapping(date) -> bool:
    return date.year


def classify_line(line: str) -> int:
    if line.startswith(" "):
        return 1
    else:
        return 0


config.set_path_predicate(path_predicate)
config.set_sample_predicate(sample_predicate)
config.set_period_mapping(period_mapping)
config.set_line_classifier(classify_line)
