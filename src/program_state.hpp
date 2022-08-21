/// \file program_state.hpp \brief Main code analysis state and
/// configuration classes

#ifndef PROGRAM_STATE_HPP
#define PROGRAM_STATE_HPP

#include <unordered_set>
#include <algorithm>
#include <chrono>

#include <boost/log/trivial.hpp>
#include <boost/date_time/gregorian/gregorian.hpp>
#include <boost/date_time/posix_time/posix_time.hpp>
#include <boost/describe.hpp>
#include <boost/mp11.hpp>

#include "common.hpp"
#include "git_interface.hpp"
#include "git_ir.hpp"

using Logger = boost::log::sources::severity_logger<
    boost::log::trivial::severity_level>;

using Date         = boost::gregorian::date;
using PTime        = boost::posix_time::ptime;
using TimeDuration = boost::posix_time::time_duration;
namespace stime    = std::chrono;
namespace bd       = boost::describe;

template <class T>
struct fmt::formatter<
    T,
    char,
    std::enable_if_t<
        boost::describe::has_describe_bases<T>::value &&
        boost::describe::has_describe_members<T>::value &&
        !std::is_union<T>::value>> {
    constexpr auto parse(format_parse_context& ctx) {
        auto it = ctx.begin(), end = ctx.end();

        if (it != end && *it != '}') {
            ctx.error_handler().on_error("invalid format");
        }

        return it;
    }

    auto format(T const& t, format_context& ctx) const {
        using namespace boost::describe;

        using Bd = describe_bases<T, mod_any_access>;
        using Md = describe_members<T, mod_any_access>;

        auto out = ctx.out();

        *out++ = '{';

        bool first = true;

        boost::mp11::mp_for_each<Bd>([&](auto D) {
            if (!first) { *out++ = ','; }

            first = false;

            out = fmt::format_to(
                out, " {}", (typename decltype(D)::type const&)t);
        });

        boost::mp11::mp_for_each<Md>([&](auto D) {
            if (!first) { *out++ = ','; }

            first = false;

            out = fmt::format_to(out, " .{}={}", D.name, t.*D.pointer);
        });

        if (!first) { *out++ = ' '; }

        *out++ = '}';

        return out;
    }
};

template <class T>
struct fmt::formatter<
    T,
    char,
    std::enable_if_t<
        boost::describe::has_describe_enumerators<T>::value>> {
  private:
    using U = std::underlying_type_t<T>;

    fmt::formatter<fmt::string_view, char> sf_;
    fmt::formatter<U, char>                nf_;

  public:
    constexpr auto parse(format_parse_context& ctx) {
        auto i1 = sf_.parse(ctx);
        auto i2 = nf_.parse(ctx);

        if (i1 != i2) { ctx.error_handler().on_error("invalid format"); }

        return i1;
    }

    auto format(T const& t, format_context& ctx) const {
        char const* s = boost::describe::enum_to_string(t, 0);

        if (s) {
            return sf_.format(s, ctx);
        } else {
            return nf_.format(static_cast<U>(t), ctx);
        }
    }
};

enum class Analytics {
    BlameBurndown,  /// Use git blame for commits allowed by the
                    /// filter script
    CommitDiffInfo, /// Which files where touched in each commit,
                    /// how many lines were edited
    Commits         /// Only information about commits
};

BOOST_DESCRIBE_ENUM(Analytics, BlameBurndown, Commits, CommitDiffInfo);

template <typename E>
concept IsDescribedEnum = bd::has_describe_enumerators<E>::value;

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
    Str            repo;
    Str            heads;
    Vec<Analytics> analytics;

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

    bool use_analytics(Analytics which) const {
        return analytics.empty() ||
               std::find(analytics.begin(), analytics.end(), which) !=
                   analytics.end();
    }
};


using TimePoint = stime::time_point<stime::system_clock>;


/// Mutable state passed around walker configurations
struct walker_state {
    CP<walker_config> config;

    git_revwalk* walker;
    /// Current git repository
    git_repository* repo;

    /// Ordered list of commits that were considered for the processing run
    Vec<git_oid>                              full_commits;
    std::unordered_map<git_oid, ir::CommitId> commit_ids;
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

    void add_id_mapping(CR<git_oid> oid, ir::CommitId id) {
        commit_ids.insert({oid, id});
    }

    ir::CommitId get_id(CR<git_oid> oid) { return commit_ids.at(oid); }


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
    std::unordered_map<git_oid, ir::CommitId> sampled_commits;

    std::mutex           m;
    ir::content_manager* content;
    SPtr<Logger>         logger;
};

#endif // PROGRAM_STATE_HPP
