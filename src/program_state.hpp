/// \file program_state.hpp \brief Main code analysis state and
/// configuration classes

#ifndef PROGRAM_STATE_HPP
#define PROGRAM_STATE_HPP

#include <unordered_set>
#include <chrono>

#include <boost/log/trivial.hpp>
#include <boost/date_time/gregorian/gregorian.hpp>
#include <boost/date_time/posix_time/posix_time.hpp>


#include "common.hpp"
#include "git_interface.hpp"
#include "git_ir.hpp"

using Logger = boost::log::sources::severity_logger<
    boost::log::trivial::severity_level>;

using Date         = boost::gregorian::date;
using PTime        = boost::posix_time::ptime;
using TimeDuration = boost::posix_time::time_duration;
namespace stime    = std::chrono;

template <>
struct fmt::formatter<Date> : fmt::formatter<Str> {
    auto format(CR<Date> date, fmt::format_context& ctx) const {
        return fmt::formatter<Str>::format(
            boost::gregorian::to_iso_extended_string(date), ctx);
    }
};


template <>
struct fmt::formatter<PTime> : fmt::formatter<Str> {
    auto format(CR<PTime> time, fmt::format_context& ctx) const {
        return fmt::formatter<Str>::format(
            boost::posix_time::to_iso_extended_string(time), ctx);
    }
};

struct walker_config {
    /// Analyse commits via subprocess launches or via libgit blame
    /// execution
    bool use_subprocess = true;
    enum threading_mode { async, defer, sequential };
    threading_mode use_threading = threading_mode::async;
    /// Current project root path (absolute path)
    Str repo;
    Str heads;

    Str  db_path;
    bool try_incremental;
    bool log_progress_bars;

    /// Allow processing of a specific path in the repository
    Func<bool(CR<Str>)> allow_path;
    /// Get integer index of the period for Date
    Func<int(CR<PTime>)> get_commit_period;
    Func<int(CR<PTime>)> get_sampled_period;
    /// Check whether commits at the specified date should be analysed
    Func<bool(CR<PTime>, CR<Str>, CR<Str>)> allow_sample;
    Func<int(CR<Str>)>                      classify_line;
};


using TimePoint = stime::time_point<stime::system_clock>;


/// Mutable state passed around walker configurations
struct walker_state {
    CP<walker_config> config;

    git_revwalk* walker;
    /// Current git repository
    git_repository* repo;

    /// Ordered list of commits that were considered for the processing run
    Vec<git_oid> full_commits;
    /// Mapping from the commit id to it's position in the whole list of
    /// considered commits
    std::unordered_map<git_oid, int> rev_index;
    /// Mapping from the commits to the analysis periods they are in
    std::unordered_map<git_oid, int> rev_periods;

    /// Add preiod mapping of the commit to the walker. All information
    /// about line's *origin period* in further analysis will be based on
    /// the data provided to to this functino.
    void add_full_commit(
        CR<git_oid> oid,   ///< git ID of the commit
        int         period ///< Period ID that this commit belongs to
    ) {
        rev_index.insert({oid, full_commits.size()});
        rev_periods.insert({oid, period});
        full_commits.push_back(oid);
    }

    /// Get period that commit is attributed to. May return 'none' option
    /// for commits that were not registered in the revese period index -
    /// ones that come from a different branch that we didn't iterate over.
    Opt<int> get_period(CR<git_oid> commit) const noexcept {
        // NOTE dynamically patching table of missing commits each time an
        // unknown is encountered is possible, but undesirable.
        auto found = rev_periods.find(commit);
        if (found != rev_periods.end()) {
            return Opt<int>{found->second};
        } else {
            return Opt<int>{};
        }
    }

    int get_period(CR<git_oid> commit, CR<git_oid> line) const noexcept {
        auto lp = get_period(line);
        auto cp = get_period(commit);
        return lp.value_or(cp.value());
    }

    /// Whether to consider commit referred to by \arg commit_id has
    /// changed in the same period as the line (\arg line_changed_id).
    ///
    /// If line comes from an unknow commit (different branch for example)
    /// it is considered changed.
    auto consider_changed(
        CR<git_oid> commit_id,
        CR<git_oid> line_change_id) const -> bool {
        auto commit = get_period(commit_id);
        auto line   = get_period(line_change_id);
        if (line) {
            return line.value() == commit.value();
        } else {
            return true;
        }
    }

    /// List of commits that were selected for the processing run
    std::unordered_set<git_oid> sampled_commits;

    std::mutex           m;
    ir::content_manager* content;
    SPtr<Logger>         logger;
};

#endif // PROGRAM_STATE_HPP
