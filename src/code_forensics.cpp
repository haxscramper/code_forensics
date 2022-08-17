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


#include "python_interop.hpp"
#include "cli_options.hpp"
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
