#include "common.hpp"
#include "git_ir.hpp"

#include <exception>
#include <string>
#include <map>
#include <fstream>
#include <thread>
#include <mutex>
#include <shared_mutex>
#include <algorithm>
#include <future>
#include <sstream>
#include <optional>
#include <semaphore>
#include <unordered_map>
#include <unordered_set>
#include <set>


#include <boost/thread/mutex.hpp>
#include <boost/thread/lock_guard.hpp>
#include <boost/lexical_cast.hpp>

#include <boost/program_options.hpp>


#include <boost/python.hpp>

#include <datetime.h>


#include "git_interface.hpp"
#include "logging.hpp"
#include "repo_processing.hpp"

using namespace boost;


using namespace git;


#define GIT_SUCCESS 0


void load_content(walker_config* config, ir::content_manager& content) {
    auto storage = ir::create_db(config->db_path);
    storage.sync_schema();
    for (CR<ir::orm_line> line : storage.iterate<ir::orm_line>()) {
        // Explicitly specifying template parameters to use slicing for the
        // second argument.
        content.multi.insert<ir::LineId, ir::LineData>(line.id, line);
    }

    for (CR<ir::orm_commit> commit : storage.iterate<ir::orm_commit>()) {
        content.multi.insert<ir::CommitId, ir::Commit>(commit.id, commit);
    }

    for (CR<ir::orm_file> file : storage.iterate<ir::orm_file>()) {
        content.multi.insert<ir::FileId, ir::File>(file.id, file);
    }

    for (CR<ir::orm_dir> dir : storage.iterate<ir::orm_dir>()) {
        content.multi.insert<ir::DirectoryId, ir::Directory>(dir.id, dir);
    }

    for (CR<ir::orm_string> str : storage.iterate<ir::orm_string>()) {
        content.multi.insert<ir::StringId, ir::String>(str.id, str);
    }
}

void store_content(walker_state* state, CR<ir::content_manager> content) {
    // Create storage connection
    auto storage = ir::create_db(state->config->db_path);
    // Sync with stored data
    storage.sync_schema();
    // Start the transaction - all data is inserted in bulk
    storage.begin_transaction();

    // Remove all previously stored data
    //
    // NOTE due to foreign key constraints on the database the order is
    // very important, otherwise deletion fails with `FOREIGN KEY
    // constraint failed` error
    //
    // HACK I temporarily removed all the foreign key constraints from the
    // ORM description, because it continued to randomly fail, even though
    // object ordering worked as expected. Maybe in the future I will fix
    // it back, but for now this piece of garbage can be ordered in any
    // way.
    if (!state->config->try_incremental) {
        LOG_I(state) << "Non-incremental update, cleaning up the database";
        storage.remove_all<ir::orm_line>();
        storage.remove_all<ir::orm_file>();
        storage.remove_all<ir::orm_commit>();
        storage.remove_all<ir::orm_lines_table>();
        storage.remove_all<ir::orm_changed_range>();
        storage.remove_all<ir::orm_dir>();
        storage.remove_all<ir::orm_author>();
        storage.remove_all<ir::orm_string>();
    } else {
        LOG_I(state) << "Incremental update, reusing the database";
    }

    {
        auto max = content.multi.store<ir::String>().size();
        INIT_PROGRESS_BAR(strings, counter, max);
        for (const auto& [id, string] :
             content.multi.store<ir::String>().pairs()) {
            storage.insert(ir::orm_string(id, ir::String{*string}));
            if (state->config->log_progress_bars) {
                tick_next(strings, counter, max, "strings");
            }
        }

        if (state->config->log_progress_bars) {
            strings.mark_as_completed();
        }
    }

    {
        auto max = content.multi.store<ir::Author>().size();
        INIT_PROGRESS_BAR(authors, counter, max);
        for (const auto& [id, author] :
             content.multi.store<ir::Author>().pairs()) {
            storage.insert(ir::orm_author(id, *author));
            if (state->config->log_progress_bars) {
                tick_next(authors, counter, max, "authors");
            }
        }
        if (state->config->log_progress_bars) {
            authors.mark_as_completed();
        }
    }

    {

        auto max = content.multi.store<ir::LineData>().size();
        INIT_PROGRESS_BAR(authors, counter, max);
        for (const auto& [id, line] :
             content.multi.store<ir::LineData>().pairs()) {
            storage.insert(ir::orm_line(id, *line));
            if (state->config->log_progress_bars) {
                tick_next(authors, counter, max, "unique lines");
            }
        }

        if (state->config->log_progress_bars) {
            authors.mark_as_completed();
        }
    }
    {

        auto max = content.multi.store<ir::Commit>().size();
        INIT_PROGRESS_BAR(authors, counter, max);
        for (const auto& [id, commit] :
             content.multi.store<ir::Commit>().pairs()) {
            storage.insert(ir::orm_commit(id, *commit));
            if (state->config->log_progress_bars) {
                tick_next(authors, counter, max, "commits");
            }
        }

        if (state->config->log_progress_bars) {
            authors.mark_as_completed();
        }
    }
    {

        auto max = content.multi.store<ir::Directory>().size();
        INIT_PROGRESS_BAR(authors, counter, max);
        for (const auto& [id, dir] :
             content.multi.store<ir::Directory>().pairs()) {
            storage.insert(ir::orm_dir(id, *dir));
            if (state->config->log_progress_bars) {
                tick_next(authors, counter, max, "directories");
            }
        }

        if (state->config->log_progress_bars) {
            authors.mark_as_completed();
        }
    }
    {
        auto max = content.multi.store<ir::File>().size();
        INIT_PROGRESS_BAR(authors, counter, max);
        for (const auto& [id, file] :
             content.multi.store<ir::File>().pairs()) {
            storage.insert(ir::orm_file(id, *file));
            for (int idx = 0; idx < file->lines.size(); ++idx) {
                storage.insert(ir::orm_lines_table{
                    .file = id, .index = idx, .line = file->lines[idx]});
            }

            for (int idx = 0; idx < file->changed_ranges.size(); ++idx) {
                storage.insert(ir::orm_changed_range{
                    file->changed_ranges[idx], .file = id, .index = idx});
            }

            if (state->config->log_progress_bars) {
                tick_next(authors, counter, max, "files");
            }
        }

        if (state->config->log_progress_bars) {
            authors.mark_as_completed();
        }
    }
    storage.commit();
}


using namespace boost::program_options;
namespace py = boost::python;

class PyForensics {
    py::object   path_predicate;
    py::object   period_mapping;
    py::object   sample_predicate;
    py::object   line_classifier;
    SPtr<Logger> logger;

  public:
    void set_logger(SPtr<Logger> log) { logger = log; }

    void log_info(CR<Str> text) { LOG_I(logger) << text; }
    void log_warning(CR<Str> text) { LOG_W(logger) << text; }
    void log_trace(CR<Str> text) { LOG_T(logger) << text; }
    void log_debug(CR<Str> text) { LOG_D(logger) << text; }
    void log_error(CR<Str> text) { LOG_E(logger) << text; }
    void log_fatal(CR<Str> text) { LOG_F(logger) << text; }

    void set_line_classifier(py::object classifier) {
        line_classifier = classifier;
    }

    void set_path_predicate(py::object predicate) {
        path_predicate = predicate;
    }

    void set_period_mapping(py::object mapping) {
        period_mapping = mapping;
    }

    void set_sample_predicate(py::object predicate) {
        sample_predicate = predicate;
    }

    bool allow_path(CR<Str> path) const {
        if (path_predicate) {
            return py::extract<bool>(path_predicate(path));
        } else {
            return true;
        }
    }

    int get_period(CR<PTime> date) const {
        if (period_mapping) {
            return py::extract<int>(period_mapping(date));
        } else {
            return 0;
        }
    }

    bool allow_sample_at_date(CR<PTime> date, CR<Str> author, CR<Str> id)
        const {
        if (sample_predicate) {
            return py::extract<bool>(sample_predicate(date, author, id));
        } else {
            return true;
        }
    }

    int classify_line(CR<Str> line) const {
        if (line_classifier) {
            return py::extract<int>(line_classifier(line));
        } else {
            return 0;
        }
    }
};

template <typename T>
struct type_into_python {
    static PyObject* convert(T const&);
};

template <typename T>
struct type_from_python {
    type_from_python() {
        py::converter::registry::push_back(
            convertible, construct, py::type_id<T>());
    }

    static void* convertible(PyObject* obj);

    static void construct(
        PyObject*                                      obj,
        py::converter::rvalue_from_python_stage1_data* data);
};

template <>
PyObject* type_into_python<PTime>::convert(CR<PTime> t) {
    auto d    = t.date();
    auto tod  = t.time_of_day();
    auto usec = tod.total_microseconds() % 1000000;
    return PyDateTime_FromDateAndTime(
        d.year(),
        d.month(),
        d.day(),
        tod.hours(),
        tod.minutes(),
        tod.seconds(),
        usec);
}

template <>
void* type_from_python<PTime>::convertible(PyObject* obj) {
    return PyDateTime_Check(obj) ? obj : nullptr;
}

template <>
void type_from_python<PTime>::construct(
    PyObject*                                      obj,
    py::converter::rvalue_from_python_stage1_data* data) {
    auto storage = reinterpret_cast<
                       py::converter::rvalue_from_python_storage<PTime>*>(
                       data)
                       ->storage.bytes;
    Date date_only(
        PyDateTime_GET_YEAR(obj),
        PyDateTime_GET_MONTH(obj),
        PyDateTime_GET_DAY(obj));
    TimeDuration time_of_day(
        PyDateTime_DATE_GET_HOUR(obj),
        PyDateTime_DATE_GET_MINUTE(obj),
        PyDateTime_DATE_GET_SECOND(obj));
    time_of_day += posix_time::microsec(
        PyDateTime_DATE_GET_MICROSECOND(obj));
    new (storage) PTime(date_only, time_of_day);
    data->convertible = storage;
}

template <>
PyObject* type_into_python<Date>::convert(Date const& d) {
    return PyDate_FromDate(d.year(), d.month(), d.day());
}

template <>
void* type_from_python<Date>::convertible(PyObject* obj) {
    return PyDate_Check(obj) ? obj : nullptr;
}

template <>
void type_from_python<Date>::construct(
    PyObject*                                      obj,
    py::converter::rvalue_from_python_stage1_data* data) {
    auto storage = reinterpret_cast<
                       py::converter::rvalue_from_python_storage<Date>*>(
                       data)
                       ->storage.bytes;
    new (storage) Date(
        PyDateTime_GET_YEAR(obj),
        PyDateTime_GET_MONTH(obj),
        PyDateTime_GET_DAY(obj));
    data->convertible = storage;
}

BOOST_PYTHON_MODULE(forensics) {
    PyDateTime_IMPORT;

    py::to_python_converter<PTime, type_into_python<PTime>>();
    type_from_python<PTime>();

    py::to_python_converter<Date, type_into_python<Date>>();
    type_from_python<Date>();

    py::object class_creator =
        //
        py::class_<PyForensics>("Forensics") //
            .def("log_info", &PyForensics::log_info, py::args("text"))
            .def(
                "log_warning", &PyForensics::log_warning, py::args("text"))
            .def("log_trace", &PyForensics::log_trace, py::args("text"))
            .def("log_debug", &PyForensics::log_debug, py::args("text"))
            .def("log_error", &PyForensics::log_error, py::args("text"))
            .def("log_fatal", &PyForensics::log_fatal, py::args("text"))
            .def(
                "set_line_classifier",
                &PyForensics::set_line_classifier,
                py::args("classifier"))
            .def(
                "set_path_predicate",
                &PyForensics::set_path_predicate,
                py::args("predicate"))
            .def(
                "set_period_mapping",
                &PyForensics::set_period_mapping,
                py::args("mapping"))
            .def(
                "set_sample_predicate",
                &PyForensics::set_sample_predicate,
                py::args("predicate"));

    py::object module_level_object = class_creator();
    py::scope().attr("config")     = module_level_object;
}

// https://stackoverflow.com/questions/51723237/boostprogram-options-bool-switch-used-multiple-times
// bool options is taken from this SO question - it is not /exactly/ what I
// aimed for, but this solution allows specifying =true or =false on the
// command line explicitly, which I aimed for

class BoolOption {
  public:
    BoolOption(bool initialState = false) : state(initialState) {}
    bool getState() const { return state; }
    void switchState() { state = !state; }
         operator bool() const { return state; }

  private:
    bool state;
};

namespace boost {
template <>
bool lexical_cast<bool, Str>(const Str& arg) {
    return arg == "true" || arg == "on" || arg == "1";
}

template <>
Str lexical_cast<Str, bool>(const bool& b) {
    std::ostringstream ss;
    ss << std::boolalpha << b;
    return ss.str();
}
} // namespace boost


void validate(boost::any& v, Vec<Str> const& xs, BoolOption* opt, long) {
    fmt::print("Provided validation values {}\n", xs);
    if (v.empty()) {
        // I don't know how to assign default here so this works only when
        // default is false
        v = BoolOption(true);
    } else {
        v = BoolOption(lexical_cast<bool>(xs[0]));
    }
}


auto parse_cmdline(int argc, const char** argv) -> variables_map {
    variables_map                  vm;
    options_description            desc{"Options"};
    positional_options_description pos{};

    desc.add_options()
        //
        ("help,h", "Help screen") //
        ("logfile",
         value<Str>()->default_value("/tmp/git_user.log"),
         "Log file location") //
        ("branch",
         value<Str>()->default_value("master"),
         "Repository branch to analyse") //
        ("incremental",
         value<BoolOption>()->default_value(BoolOption(false), "false"),
         "Load previosly created database and only process commits that "
         "were not registered previously") //
        ("outfile",
         value<Str>(),
         "Output file location. If not supplied output will be "
         "generated based on the input repo location")(
            "allowed",
            value<Vec<Str>>(),
            "List of globs for allowed paths") //
        ("config",
         value<Vec<Str>>(),
         "Config file where options may be specified (can be specified "
         "more than once)") //
        ("log-progress",
         value<BoolOption>()->default_value(BoolOption(true), "true"),
         "Show dynamic progress bars for operations") //
        ("blame-subprocess",
         value<BoolOption>()->default_value(BoolOption(true), "true"),
         "Use blame for subprocess")                    //
        ("repo", value<Str>(), "Input repository path") //
        ("filter-script",
         value<Str>(),
         "User-provided python script that configures code forensics "
         "filter")
        //
        ;

    pos.add("repo", 1);

    try {
        store(
            command_line_parser(argc, argv)
                .options(desc)
                .positional(pos)
                .run(),
            vm);

        if (vm.count("help")) {
            std::cout << desc << "\n";
            exit(0);
        }

        if (vm.count("config") > 0) {
            for (const auto& config : vm["config"].as<Vec<Str>>()) {
                std::ifstream ifs{config};

                if (ifs.fail()) {
                    std::cerr << "Error opening config file: " << config
                              << std::endl;
                    exit(1);
                }

                store(parse_config_file(ifs, desc), vm);
            }
        }

        notify(vm);

    } catch (const error& ex) {
        std::cerr << ex.what() << "\n";
        exit(1);
    }


    return vm;
}

void init_logger_properties() {
    // Add some attributes too
    log::core::get()->add_global_attribute(
        "TimeStamp", log::attrs::local_clock());
    log::core::get()->add_global_attribute(
        "RecordID", log::attrs::counter<unsigned int>());

    log::core::get()->add_global_attribute("File", MutLog<Str>(""));
    log::core::get()->add_global_attribute("Func", MutLog<Str>(""));
    log::core::get()->add_global_attribute("Line", MutLog<int>(0));
}

/// Parses the value of the active python exception
/// NOTE SHOULD NOT BE CALLED IF NO EXCEPTION
Str parse_python_exception() {
    PyObject *type_ptr = NULL, *value_ptr = NULL, *traceback_ptr = NULL;
    // Fetch the exception info from the Python C API
    PyErr_Fetch(&type_ptr, &value_ptr, &traceback_ptr);

    // Fallback error
    Str ret("Unfetchable Python error");
    // If the fetch got a type pointer, parse the type into the exception
    // string
    if (type_ptr != NULL) {
        py::handle<> h_type(type_ptr);
        py::str      type_pstr(h_type);
        // Extract the string from the boost::python object
        py::extract<Str> e_type_pstr(type_pstr);
        // If a valid string extraction is available, use it
        //  otherwise use fallback
        if (e_type_pstr.check()) {
            ret = e_type_pstr();
        } else {
            ret = "Unknown exception type";
        }
    }
    // Do the same for the exception value (the stringification of the
    // exception)
    if (value_ptr != NULL) {
        py::handle<>     h_val(value_ptr);
        py::str          a(h_val);
        py::extract<Str> returned(a);
        if (returned.check()) {
            ret += ": " + returned();
        } else {
            ret += Str(": Unparseable Python error: ");
        }
    }
    // Parse lines from the traceback using the Python traceback module
    if (traceback_ptr != NULL) {
        py::handle<> h_tb(traceback_ptr);
        // Load the traceback module and the format_tb function
        py::object tb(py::import("traceback"));
        py::object fmt_tb(tb.attr("format_tb"));
        // Call format_tb to get a list of traceback strings
        py::object tb_list(fmt_tb(h_tb));
        // Join the traceback strings into a single string
        py::object tb_str(py::str("\n").join(tb_list));
        // Extract the string, check the extraction, and fallback in
        // necessary
        py::extract<Str> returned(tb_str);
        if (returned.check()) {
            ret += ": " + returned();
        } else {
            ret += Str(": Unparseable Python traceback");
        }
    }
    return ret;
}

// inline void PrintUsage(const options_description desc) {
//     std::cout << "Usage: " << app_name << " [options]" << std::endl;
//     std::cout << "    App description" << std::endl;
//     std::cout << desc << std::endl;
//     std::cout << std::endl << "v" << VERSION << std::endl;
// }

inline void PrintVariableMap(const variables_map vm) {
    for (auto& it : vm) {
        std::cout << "> " << it.first;
        if (((boost::any)it.second.value()).empty()) {
            std::cout << "(empty)";
        }
        if (vm[it.first].defaulted() || it.second.defaulted()) {
            std::cout << "(default)";
        }
        std::cout << "=";

        bool is_char;
        try {
            boost::any_cast<const char*>(it.second.value());
            is_char = true;
        } catch (const boost::bad_any_cast&) { is_char = false; }
        bool is_str;
        try {
            boost::any_cast<std::string>(it.second.value());
            is_str = true;
        } catch (const boost::bad_any_cast&) { is_str = false; }

        if (((boost::any)it.second.value()).type() == typeid(int)) {
            std::cout << vm[it.first].as<int>() << std::endl;
        } else if (
            ((boost::any)it.second.value()).type() == typeid(bool)) {
            std::cout << vm[it.first].as<bool>() << std::endl;
        } else if (
            ((boost::any)it.second.value()).type() == typeid(double)) {
            std::cout << vm[it.first].as<double>() << std::endl;
        } else if (is_char) {
            std::cout << vm[it.first].as<const char*>() << std::endl;
        } else if (is_str) {
            std::string temp = vm[it.first].as<std::string>();
            if (temp.size()) {
                std::cout << temp << std::endl;
            } else {
                std::cout << "true" << std::endl;
            }
        } else { // Assumes that the only remainder is vector<string>
            try {
                std::vector<std::string>
                     vect = vm[it.first].as<std::vector<std::string>>();
                uint i    = 0;
                for (std::vector<std::string>::iterator oit = vect.begin();
                     oit != vect.end();
                     oit++, ++i) {
                    std::cout << "\r> " << it.first << "[" << i
                              << "]=" << (*oit) << std::endl;
                }
            } catch (const boost::bad_any_cast&) {
                std::cout << "UnknownType("
                          << ((boost::any)it.second.value()).type().name()
                          << ")" << std::endl;
            }
        }
    }
}

auto main(int argc, const char** argv) -> int {
    auto vm = parse_cmdline(argc, argv);
    PrintVariableMap(vm);

    auto file_sink = create_file_sink(vm["logfile"].as<Str>());
    auto out_sink  = create_std_sink();

    out_sink->set_filter(severity >= log::severity::info);

    finally close_out_sink{[&out_sink]() {
        out_sink->stop();
        out_sink->flush();
    }};

    finally close_file_sink{[&file_sink]() {
        file_sink->stop();
        file_sink->flush();
    }};

    auto logger = std::make_shared<Logger>();

    Str in_repo    = vm["repo"].as<Str>();
    Str in_branch  = vm["branch"].as<Str>();
    Str in_outfile = vm.count("outfile") ? vm["outfile"].as<Str>()
                                         : "/tmp/db.sqlite";

    log::core::get()->add_sink(file_sink);
    log::core::get()->add_sink(out_sink);
    init_logger_properties();

    const bool use_fusion = false;

    bool in_blame_subprocess = vm["blame-subprocess"].as<BoolOption>();
    LOG_I(logger) << fmt::format(
        "Use blame subprocess for file analysis: {}", in_blame_subprocess);

    auto in_script = vm.count("filter-script")
                         ? vm["filter-script"].as<Str>()
                         : "";

    PyForensics* forensics;
    // Register user-defined module in python - this would allow importing
    // `forensics` module in the C++ side of the application
    PyImport_AppendInittab("forensics", &PyInit_forensics);
    // Initialize main python library part
    Py_Initialize();
    if (in_script.empty()) {
        forensics = new PyForensics();
        LOG_W(logger)
            << "No filter script was provided - analysing all commits in "
               "the whole repository might be slow for large projects";

    } else {
        LOG_I(logger) << "User-defined filter configuration was provided, "
                         "evaluating "
                      << in_script;
        Path path{in_script};
        if (fs::exists(path)) {
            py::object main_module = py::import("__main__");
            py::object name_space  = main_module.attr("__dict__");

            try {
                // Get the configuration module object
                py::object forensics_module = py::import("forensics");
                // Retrieve config pointer object from it
                py::object config_object = forensics_module.attr(
                    "__dict__")["config"];
                // Extract everything to a pointer
                forensics = py::extract<PyForensics*>(config_object);
                if (forensics == nullptr) {
                    LOG_F(logger) << "Could not extract pointer for "
                                     "forensics configuration object";
                    return 1;
                }

                forensics->set_logger(logger);

                auto abs = fs::absolute(path);
                LOG_T(logger) << "Python file, executing as expected, "
                                 "absolute path is "
                              << abs.c_str();


                auto result = py::exec_file(
                    py::str(abs.c_str()), name_space, name_space);


                LOG_D(logger) << "Execution of the configuration script "
                                 "was successfull";

            } catch (py::error_already_set& err) {

#define LOG_PY_ERROR(logger)                                              \
    {                                                                     \
        auto exception = parse_python_exception();                        \
        LOG_E(logger) << "Error during python code execution";            \
        LOG_E(logger) << exception;                                       \
    }

                LOG_PY_ERROR(logger);

                return 1;
            }

        } else {
            LOG_E(logger)
                << "User configuration file script does not exist "
                << path.native() << " no such file or directory";
            return 1;
        }
    }

    assert(vm["log-progress"].as<BoolOption>() == false);

    // Provide implementation callback strategies
    auto config = UPtr<walker_config>(new walker_config{
        .use_subprocess = in_blame_subprocess,
        // Full process parallelization
        .use_threading     = walker_config::async,
        .repo              = in_repo,
        .heads             = fmt::format(".git/refs/heads/{}", in_branch),
        .db_path           = in_outfile,
        .try_incremental   = vm["incremental"].as<BoolOption>(),
        .log_progress_bars = vm["log-progress"].as<BoolOption>(),
        .allow_path        = [&logger, forensics](CR<Str> path) -> bool {
            try {
                return forensics->allow_path(path);
            } catch (py::error_already_set& err) {
                LOG_PY_ERROR(logger);
                return false;
            }
        },
        .get_period = [&logger, forensics](CR<PTime> date) -> int {
            try {
                return forensics->get_period(date);
            } catch (py::error_already_set& err) {
                LOG_PY_ERROR(logger);
                return 0;
            }
        },
        .allow_sample =
            [&logger, forensics](
                CR<PTime> date, CR<Str> author, CR<Str> id) -> bool {
            try {
                return forensics->allow_sample_at_date(date, author, id);
            } catch (py::error_already_set& err) {
                LOG_PY_ERROR(logger);
                return false;
            }
        },
        .classify_line = [&logger, forensics](CR<Str> line) -> int {
            try {
                return forensics->classify_line(line);
            } catch (py::error_already_set& err) {
                LOG_PY_ERROR(logger);
                return 0;
            }
        }});

    libgit2_init();
    // Check whether threads can be enabled
    assert(libgit2_features() & GIT_FEATURE_THREADS);

    auto heads_path = Path{config->repo} / config->heads;
    if (!fs::exists(config->repo)) {
        LOG_F(logger) << "Input directory '" << config->repo
                      << "' does not exist, aborting analysis";
        return 1;
    } else if (!fs::exists(heads_path)) {
        LOG_F(logger) << "The branch '" << in_branch
                      << "' does not exist in the repository at path "
                      << config->repo << " the full path " << heads_path
                      << " does not exist";
        return 1;
    }

    ir::content_manager content;
    // Create main walker state used in the whole commit analysis state
    auto state = UPtr<walker_state>(new walker_state{
        .config  = config.get(),
        .repo    = repository_open_ext(config->repo.c_str(), 0, nullptr),
        .content = &content,
        .logger  = logger});

    if (config->try_incremental) {
        if (std::filesystem::exists(config->db_path)) {
            load_content(config.get(), content);
        } else {
            LOG_W(state) << "cannot load incremental from the path "
                         << config->db_path;
        }
    }

    git_oid oid;
    // Initialize state of the commit walker
    open_walker(oid, *state);
    // Store finalized commit IDs from executed tasks
    Vec<ir::CommitId> commits{};
    auto              result = launch_analysis(oid, state.get());
    for (auto& commit : result) {
        commits.push_back(commit);
    }

    LOG_I(state) << "Finished analysis, writing database";
    store_content(state.get(), content);

    LOG_I(state) << "Finished execution, DB written successfully";

    Py_Finalize();
    return 0;
}
