#include "logging.hpp"


using namespace indicators;
BlockProgressBar init_progress(int max) {
    return BlockProgressBar{
        option::BarWidth{60},
        option::ForegroundColor{Color::white},
        option::FontStyles{std::vector<FontStyle>{FontStyle::bold}},
        option::MaxProgress{max}};
}

void tick_next(BlockProgressBar& bar, int& count, int max, CR<Str> name) {
    bar.set_option(BarText{fmt::format("{}/{} {}", ++count, max, name)});
    bar.tick();
}

void log_formatter(
    const boost::log::record_view&  rec,
    boost::log::formatting_ostream& strm) {

    std::filesystem::path file{logging::extract<Str>("File", rec).get()};

    strm << fmt::format(
        "[{}]", logging::extract<PTime>("TimeStamp", rec).get());

    // strm    << " at " << file.filename().native()
    //     << ":" << logging::extract<int>("Line", rec);

    strm << std::setw(4)
         << logging::extract<unsigned int>("RecordID", rec)         //
         << ": " << std::setw(7) << rec[logging::trivial::severity] //
         << " " << rec[logging::expr::smessage];
}

Pair<char, fmt::v9::text_style> format_style(boost::log::severity level) {
    switch (level) {
        case logging::severity::warning:
            return {'W', fmt::fg(fmt::color::yellow)};
        case logging::severity::info:
            return {'I', fmt::fg(fmt::color::cyan)};
        case logging::severity::fatal:
            return {
                'F', fmt::emphasis::bold | fmt::fg(fmt::color::magenta)};
        case logging::severity::error:
            return {
                'E',
                fmt::emphasis::bold | fmt::emphasis::blink |
                    fmt::fg(fmt::color::red)};
        case logging::severity::trace:
            return {'T', fmt::fg(fmt::color::white)};
        case logging::severity::debug:
            return {'D', fmt::fg(fmt::color::white)};
        default: return {'?', fmt::fg(fmt::color::white)};
    }
}

void out_formatter(
    const boost::log::record_view&  rec,
    boost::log::formatting_ostream& strm) {
    auto [color, style] = format_style(
        rec[logging::trivial::severity].get());
    strm << fmt::format("[{}] ", fmt::styled(color, style));
    strm << rec[logging::expr::smessage];
}

boost::shared_ptr<sink_t> create_file_sink(CR<Str> outfile) {
    boost::shared_ptr<std::ostream> log_stream{new std::ofstream(outfile)};
    auto backend = boost::make_shared<backend_t>();
    // Flush log file after each record is written - this is done in a
    // separate thread, so won't block the processing for too long
    // (supposedly) and creates a much nicer-looking `trail -f` run
    backend->auto_flush(true);
    boost::shared_ptr<sink_t> sink(new sink_t(
        backend,
        // We'll apply record ordering to ensure that records from
        // different threads go sequentially in the file
        logging::keywords::order = logging ::make_attr_ordering<
            unsigned int>("RecordID", std::less<unsigned int>())));

    sink->locked_backend()->add_stream(log_stream);
    sink->set_formatter(&log_formatter);

    return sink;
}

boost::shared_ptr<sink_t> create_std_sink() {
    auto backend = boost::make_shared<backend_t>();
    backend->auto_flush(true);
    // Backend stream must be wrapped in the shared pointer, but since we
    // are using stdout deletion itself is not necessary, so null deleter
    // is used.
    boost::shared_ptr<std::ostream> log_stream{
        &std::cout, boost::null_deleter()};
    boost::shared_ptr<sink_t> sink(new sink_t(
        backend,
        logging::keywords::order = logging ::make_attr_ordering<
            unsigned int>("RecordID", std::less<unsigned int>())));
    sink->locked_backend()->add_stream(log_stream);
    sink->set_formatter(&out_formatter);
    return sink;
}
