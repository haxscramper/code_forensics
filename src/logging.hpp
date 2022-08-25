#ifndef LOGGING_HPP
#define LOGGING_HPP

#include <unordered_set>
#include <fstream>
#include <chrono>

#include <boost/log/trivial.hpp>
#include <boost/log/common.hpp>
#include <boost/log/expressions.hpp>
#include <boost/log/attributes.hpp>
#include <boost/log/sinks.hpp>
#include <boost/log/sources/logger.hpp>
#include <boost/log/utility/record_ordering.hpp>
#include <boost/core/null_deleter.hpp>

#include "common.hpp"
#include "program_state.hpp"

#include <shared_mutex>

#include <indicators/progress_bar.hpp>
#include <indicators/block_progress_bar.hpp>
#include <indicators/cursor_control.hpp>

indicators::BlockProgressBar init_progress(int max, int width = 60);

using BarText = indicators::option::PostfixText;


void tick_next(
    indicators::BlockProgressBar& bar,
    int&                          count,
    int                           max,
    CR<Str>                       name,
    CR<Str>                       extra = "");


namespace logging = boost::log;

namespace boost::log {
namespace expr  = logging::expressions;
namespace attrs = logging::attributes;
}; // namespace boost::log


namespace sc = std::chrono;

struct ScopedBar {
    int                                   count = 0;
    int                                   max;
    indicators::BlockProgressBar          bar;
    Str                                   annotation;
    walker_state*                         state;
    bool                                  timed;
    sc::high_resolution_clock::time_point start;


    inline ScopedBar(
        walker_state* _state,
        int           _max,
        CR<Str>       _annotation,
        bool          _timed = true,
        int           _width = 40)
        : max(_max)
        , bar(init_progress(_max, _width))
        , state(_state)
        , annotation(_annotation)
        , timed(_timed) {
        if (state->config->log_progress_bars) {
            // Avoid verlap of the progress bar and the stdout logging.
            logging::core::get()->flush();
        }
        if (timed) { start = sc::high_resolution_clock::now(); }
    }

    inline ~ScopedBar() {
        if (state->config->log_progress_bars) { bar.mark_as_completed(); }
    }

    inline void tick() {
        if (state->config->log_progress_bars) {
            Str extra;
            if (timed) {
                sc::duration<double>
                    diff = sc::high_resolution_clock::now() - start;
                extra    = fmt::format(
                    " {:1.4f}/{:4.2f}/{:4.2f}",
                    (diff / count).count(),
                    (max - count) * (diff / count).count(),
                    diff.count());
            }
            tick_next(bar, count, max, annotation, extra);
        }
    }
};


using Logger = logging::sources::severity_logger<
    logging::trivial::severity_level>;

/// \defgroup all_logging logging macros
/// Shorthand macros to write an output to the logger
/// @{
namespace boost::log {
using severity = logging::trivial::severity_level;
}

/// Wrapper around the logger call for setting the 'File', 'Line', and
/// 'Func' attributes.
#define CUSTOM_LOG(logger, sev)                                           \
    set_get_attrib("File", Str{__FILE__});                                \
    set_get_attrib("Line", __LINE__);                                     \
    set_get_attrib("Func", Str{__PRETTY_FUNCTION__});                     \
    BOOST_LOG_SEV(logger, sev)


/// Type alias for mutable constant template used in the logging. The
/// application *might* run in the multithreaded mode, so shared mutex is
/// used for guarding access to the data.
template <typename T>
using MutLog = logging::attrs::mutable_constant<T, std::shared_mutex>;

/// Set value of the attribute and return a reference to it, for further
/// modifications.
///
/// \note The type of the value must match *exactly* with the original
/// attribute declaration - using `const char*` instead of the
/// `std::string` will result in the exception
template <typename ValueType>
auto set_get_attrib(const char* name, ValueType value) -> ValueType {
    auto attr = logging::attribute_cast<MutLog<ValueType>>(
        logging::core::get()->get_global_attributes()[name]);
    attr.set(value);
    return attr.get();
}

inline auto get_logger(walker_state* state) -> Logger& {
    return *(state->logger);
}

inline auto get_logger(UPtr<walker_state>& state) -> Logger& {
    return *(state->logger);
}

inline auto get_logger(SPtr<Logger>& in) -> Logger& { return *in; }

#define LOG_T(state)                                                      \
    CUSTOM_LOG((get_logger(state)), logging::severity::trace)
#define LOG_D(state)                                                      \
    CUSTOM_LOG((get_logger(state)), logging::severity::debug)
#define LOG_I(state)                                                      \
    CUSTOM_LOG((get_logger(state)), logging::severity::info)
#define LOG_W(state)                                                      \
    CUSTOM_LOG((get_logger(state)), logging::severity::warning)
#define LOG_E(state)                                                      \
    CUSTOM_LOG((get_logger(state)), logging::severity::error)
#define LOG_F(state)                                                      \
    CUSTOM_LOG((get_logger(state)), logging::severity::fatal)
/// @}

using backend_t = logging::sinks::text_ostream_backend;
using sink_t    = logging::sinks::asynchronous_sink<
    backend_t,
    logging::sinks::unbounded_ordering_queue<
        logging::attribute_value_ordering<
            unsigned int,
            std::less<unsigned int>>>>;

BOOST_LOG_ATTRIBUTE_KEYWORD(
    severity,
    "Severity",
    logging::trivial::severity_level)

void log_formatter(
    logging::record_view const&  rec,
    logging::formatting_ostream& strm);

Pair<char, fmt::text_style> format_style(logging::severity level);

void out_formatter(
    logging::record_view const&  rec,
    logging::formatting_ostream& strm);

boost::shared_ptr<sink_t> create_file_sink(CR<Str> outfile);

boost::shared_ptr<sink_t> create_std_sink();

void init_logger_properties();

#endif // LOGGING_HPP
