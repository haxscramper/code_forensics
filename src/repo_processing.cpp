/// \file repo_processing.cpp \brief repository processing algorithms
#include "repo_processing.hpp"
#include "logging.hpp"
#include "common.hpp"
#include "git_interface.hpp"

#include <algorithm>
#include <execution>

using namespace ir;

namespace bp = boost::process;

int get_nesting(CR<Str> line) {
    int result = 0;
    for (char c : line) {
        if (c == ' ') {
            ++result;
        } else if (c == '\t') {
            result += 4;
        } else {
            break;
        }
    }

    return result;
}

void push_line(
    FileId        id,
    walker_state* walker,
    CR<LineData>  line,
    bool          changed,
    int           period) {
    auto& file = walker->content->at(id);
    file.lines.push_back(walker->content->add(line));
    file.total_complexity += line.nesting;
    file.line_count += 1;
}

FileId stats_via_subprocess(
    git_oid       commit_oid,
    walker_state* walker,
    File          file,
    CR<Str>       relpath) {

    Str str_oid{oid_tostr(commit_oid)};

    // Getting file id immediately at the start in order to use it for the
    // line construction.
    auto result = FileId::Nil();
    {
        SLock lock{walker->m};
        result = walker->content->add(file);
    }
    /// Start git blame subprocess
    Vec<Str> args{
        bp::search_path("git").string(),
        "blame",
        "--line-porcelain",
        str_oid,
        "--",
        relpath};

    /// Read it's standard output
    bp::ipstream out;
    /// Proces is started in the specified project directory
    bp::child blame{
        args, bp::std_out > out, bp::start_dir(walker->config->repo)};

    Str line;
    // --line-porcelain generates chunks with twelve consecutive elements -
    // I'm only interested in the AuthorTime, everything else can be
    // skipped for now. Code below implements a simple state machine with
    // states encoded in the `LK` enum
    enum LK {
        Commit        = 0,
        Author        = 1,
        AuthorMail    = 2,
        AuthorTime    = 3,
        AuthorTz      = 4,
        Committer     = 5,
        CommitterMail = 6,
        CommitterTime = 7,
        CommitterTz   = 8,
        Summary       = 9,
        Previous      = 10,
        Boundary      = 11,
        Filename      = 12,
        Content       = 13
    };

    LK         state = LK::Commit;
    Str        time;
    ir::Author author;
    Str        changed_at;

    int line_counter = 0;
    while (std::getline(out, line) && !line.empty()) {
        // even for 'machine reading' output is not consistent - some parts
        // are optional and can be missing in the output, requiring extra
        // hacks for processing.
        switch (state) {
            case LK::Previous:
            case LK::Boundary: {
                if (line.starts_with("filename")) { state = LK::Filename; }
                break;
            }

            default: break;
        }

        std::stringstream is{line};

        switch (state) {
            case LK::Commit: {
                is >> changed_at;
                break;
            }

                /// For now we are only looking into the authoring time
            case LK::AuthorTime: {
                is >> time;
                assert(time == "author-time");
                is >> time;
                break;
            }

            case LK::Author: {
                is >> author.name;
                is >> author.name;
                break;
            }

            case LK::Content: {
                // Constructin a new line data using already parsed
                // elements and the file ID. Adding new line into the store
                // and immediately appending the content to the file.
                SLock   lock{walker->m};
                git_oid line_changed = git::oid_fromstr(
                    changed_at.c_str());
                push_line(
                    result,
                    walker,
                    LineData{
                        .author  = walker->content->add(author),
                        .time    = std::stol(time),
                        .content = walker->content->add(String{line}),
                        .commit  = walker->get_id(line_changed),
                        .nesting = get_nesting(line)},
                    walker->consider_changed(commit_oid, line_changed),
                    walker->get_period(commit_oid, line_changed));
                ++line_counter;
                break;
            }

            default:
                // Ignore everything else
                break;
        }

        // (ab)use decaying of the enum to integer
        state = static_cast<LK>((state + 1) % (LK::Content + 1));
    }

    // Wait until the whole process is finished
    blame.wait();
    return result;
}

FileId stats_via_libgit(
    walker_state*         state,
    git_oid               commit_oid,
    const git_tree_entry* entry,
    CR<Str>               relpath,
    File                  file) {

    auto result = FileId::Nil();
    {
        SLock lock{state->m};
        result = state->content->add(file);
    }
    // Init default blame creation options
    git_blame_options blameopts = GIT_BLAME_OPTIONS_INIT;
    // We are only interested in blame information up until target commit
    blameopts.newest_commit = commit_oid;
    // Extract git blob object
    git_object* object = git::tree_entry_to_object(state->repo, entry);
    // get blame information
    git_blame* blame = git::blame_file(
        state->repo, relpath.c_str(), &blameopts);
    assert(git::object_type(object) == GIT_OBJECT_BLOB);
    // `git_object` can be freely cast to the blob, provided we checked the
    // type first.
    auto blob = reinterpret_cast<git_blob*>(object);
    // Byte position in the blob content
    int i = 0;
    // Counter for file line iteration
    int line = 1;
    // When null hunk is encountered - complete execution
    bool break_on_null_hunk = false;
    // Get full size (in bytes) of the target blob
    git_object_size_t rawsize = git::blob_rawsize(blob);
    // Get raw content of the git blob
    const char* rawdata = static_cast<const char*>(
        git_blob_rawcontent(blob));

    // Process blob bytes - this is the only explicit delimiter we get when
    // working with blobs
    while (i < rawsize) {
        // Search for the next end of line
        const char* eol = static_cast<const char*>(
            memchr(rawdata + i, '\n', static_cast<size_t>(rawsize - i)));
        // Find input end index
        const int endpos = static_cast<int>(eol - rawdata + 1);
        // get information for the current line
        const git_blame_hunk* hunk = git::blame_get_hunk_byline(
            blame, line);

        // if hunk is empty stop processing
        if (break_on_null_hunk && hunk == nullptr) { break; }

        if (hunk != nullptr && hunk->final_signature != nullptr) {
            break_on_null_hunk = true;
            // get date when hunk had been altered
            auto ptr = (eol == nullptr) ? (rawdata + rawsize) : (eol);
            const auto size = static_cast<Str::size_type>(
                std::distance(rawdata + i, ptr));

            Str   str{rawdata + i, size};
            SLock lock{state->m};
            push_line(
                result,
                state,
                LineData{
                    .author = state->content->add(Author{}),
                    .time   = hunk->final_signature->when.time,
                    // FIXME get slice of the string for the content
                    .content = state->content->add(String{str}),
                    .commit  = state->get_id(hunk->final_commit_id),
                    .nesting = get_nesting(str)},
                state->consider_changed(commit_oid, hunk->final_commit_id),
                state->get_period(commit_oid, hunk->final_commit_id));
        }

        // Advance over raw data
        i = endpos;
        // Increment line
        line++;
    }

    // Blame information is no longer needed
    git::blame_free(blame);

    return result;
}

FileId exec_walker(
    git_oid               commit_oid,
    walker_state*         state,
    CommitId              commit,
    const char*           root,
    const git_tree_entry* entry) {

    // We are looking for blobs
    if (git::tree_entry_type(entry) != GIT_OBJECT_BLOB) {
        return FileId::Nil();
    }
    // get entry name relative to `root`
    Str path{git::tree_entry_name(entry)};
    // Create full relative path for the target object
    auto relpath = Str{root + path};
    // Check for provided predicate

    // IR has several fields that must be initialized at the start, so
    // using an optional for the file and calling init in the
    // RAII-lock-guarded section.
    Opt<File> init;

    {
        SLock lock{state->m};
        init = File{
            .commit_id = commit,
            .parent    = state->content->getDirectory(Str{root}),
            .name      = state->content->add(String{path})};
    }

    // Choose between different modes of data processing and call into one.
    FileId result = state->config->use_subprocess
                        ? stats_via_subprocess(
                              commit_oid, state, init.value(), relpath)
                        : stats_via_libgit(
                              state,
                              commit_oid,
                              entry,
                              relpath,
                              init.value());


    return result;
}

CommitId process_commit(git_oid commit_oid, walker_state* state) {
    git_commit* commit = git::commit_lookup(state->repo, &commit_oid);
    // commit information should be cleaned up when we exit the scope
    finally close{[commit]() {
        // FIXME freeing the commit causes segmentation fault and I have no
        // idea what is causing this - the issue occurs even in the
        // sequential, non-parallelized mode. The issue was introduces in
        // the commit '4e0bda9'
        //
        // commit_free(commit);
    }};

    auto hash = oid_tostr(*git_commit_id(commit));

    if (state->config->try_incremental) {
        for (auto& [id, commit] :
             state->content->multi.store<Commit>().pairs()) {
            if (commit->hash == hash) { return id; }
        }
    }

    {
        auto signature = const_cast<git_signature*>(
            git::commit_author(commit));
        finally close{[signature]() { git::signature_free(signature); }};
        return state->content->add(Commit{
            .author   = state->content->add(Author{
                  .name  = Str{signature->name},
                  .email = Str{signature->email}}),
            .time     = git::commit_time(commit),
            .timezone = git::commit_time_offset(commit),
            .hash     = hash,
            .period   = state->config->get_sampled_period(
                boost::posix_time::from_time_t(git::commit_time(commit))),
            .message = Str{git::commit_message(commit)}});
    }
}

void file_tasks(
    Vec<SubTaskParams>& treewalk,
    walker_state*       state,
    git_oid             commit_oid,
    CommitId            out_commit) {
    git_commit* commit = git::commit_lookup(state->repo, &commit_oid);
    // Get tree for a commit
    auto tree = git::commit_tree(commit);
    git::commit_free(commit);

    // walk all entries in the tree and collect them for further
    // processing.
    tree_walk(
        tree,
        // order is not particularly important, doing preorder
        // traversal here
        GIT_TREEWALK_PRE,
        // Capture all necessary data for execution and delegate the
        // implementation to the actual function.
        [&treewalk, state, out_commit, commit_oid](
            const char* root, const git_tree_entry* entry) {
            auto relpath = Str{
                Str{root} + Str{git::tree_entry_name(entry)}};
            if (!state->config->allow_path ||
                state->config->allow_path(relpath)) {
                treewalk.push_back(SubTaskParams{
                    .commit_oid = commit_oid,
                    .out_commit = out_commit,
                    .root       = Str{root},
                    .entry      = git::tree_entry_dup(entry)});
            }
            return GIT_OK;
        });
}

void open_walker(git_oid& oid, walker_state& state) {
    // Read HEAD on master
    Path head_filepath = Path{state.config->repo} /
                         Path{state.config->heads};
    // REFACTOR this part was copied from the SO example and I'm pretty
    // sure it can be implemented in a cleaner manner, but I haven't
    // touched this part yet.
    FILE*                head_fileptr = nullptr;
    std::array<char, 41> head_rev;

    if ((head_fileptr = fopen(head_filepath.c_str(), "r")) == nullptr) {
        throw std::system_error{
            std::error_code{},
            fmt::format("Error opening {}", head_filepath)};
    }

    if (fread(head_rev.data(), 40, 1, head_fileptr) != 1) {
        throw std::system_error{
            std::error_code{},
            fmt::format("Error reading from {}", head_filepath)};
        fclose(head_fileptr);
    }

    fclose(head_fileptr);

    oid = git::oid_fromstr(head_rev.data());
    // Initialize revision walker
    state.walker = git::revwalk_new(state.repo);
    // Iterate all commits in the topological order
    git::revwalk_sorting(state.walker, GIT_SORT_TOPOLOGICAL);
    git::revwalk_push(state.walker, &oid);
}


struct FullCommitData {
    git_oid     oid;
    PTime       time;
    git_commit* commit;
    CommitId    id;
};

void for_each_commit(
    walker_state*           state,
    CR<Vec<FullCommitData>> full_commits) {
    LOG_I(state) << "Getting list of files changed per each commit";
    git_commit*      prev     = nullptr;
    git_diff_options diffopts = GIT_DIFF_OPTIONS_INIT;

    struct CommitTask {
        CommitId  id;
        git_tree* prev_tree;
        git_tree* this_tree;
    };

    Vec<git_tree*>  trees;
    Vec<CommitTask> tasks;
    git_tree*       prev_tree = nullptr;

    for (const auto& [oid, date, git_commit, oid_commit] : full_commits) {
        git_tree* this_tree = git::commit_tree(git_commit);
        tasks.push_back({oid_commit, prev_tree, this_tree});
        trees.push_back(this_tree);
        prev_tree = this_tree;

        prev = git_commit;
    }

    auto bar = ScopedBar(
        state, full_commits.size(), "commits to analyze", true, 40);

    std::mutex tick_mutex;
    auto       task_executor = [state, &tick_mutex, &diffopts, &bar](
                             CR<CommitTask> task) {
        git_diff* diff = git::diff_tree_to_tree(
            state->repo, task.prev_tree, task.this_tree, &diffopts);

        auto     id_commit = task.id;
        Vec<Str> paths;
        diff_foreach(
            diff,
            DiffForeachParams{
                .file_cb = [state, id_commit, &tick_mutex, &bar, &paths](
                               const git_diff_delta* delta,
                               float                 progress,
                               void*                 payload) {
                    paths.push_back(delta->new_file.path);
                    return GIT_OK;
                }});

        SLock lock{tick_mutex};
        for (const auto& path : paths) {
            state->content->at(id_commit).changed_files.push_back(
                {state->content->add(String{path}),
                 state->content->parentDirectory(path)});
        }
    };

    const int                             max_parallel = 16;
    std::counting_semaphore<max_parallel> counting{max_parallel};
    Vec<std::future<void>>                executed;

    for (const auto& task : tasks) {
        bar.tick();
        counting.acquire();
        executed.push_back(std::async([task, &counting, &task_executor]() {
            finally finish{[&counting]() { counting.release(); }};
            task_executor(task);
        }));
    }

    for (auto& future : executed) {
        future.get();
    }
}

Vec<CommitId> launch_analysis(git_oid& oid, walker_state* state) {
    // All constructed information
    Vec<CommitId> processed{};
    // Walk over every commit in the history
    Vec<FullCommitData> full_commits;
    while (git::revwalk_next(&oid, state->walker) == 0) {
        // Get commit from the provided oid
        git_commit* commit = git::commit_lookup(state->repo, &oid);
        // Convert from unix timestamp used by git to humane format
        PTime date = boost::posix_time::from_time_t(
            git::commit_time(commit));

        auto id = process_commit(oid, state);
        full_commits.push_back({oid, date, commit, id});
        state->add_id_mapping(oid, id);

        // check if we can process it
        //
        // FIXME `commit_author` returns invalid signature here that causes
        // a segfault during conversion to a string. Otherwise
        // `commit_author(commit)->name` is the correct way (according to
        // the documentation least).
        if (state->config->allow_sample(date, "", oid_tostr(oid))) {
            int period = state->config->get_commit_period(date);
            // Store in the list of commits for sampling
            state->sampled_commits.insert({oid, id});
            LOG_T(state) << fmt::format(
                "Processing commit {} at {} into period {}",
                oid,
                date,
                period);
        }
    }

    std::reverse(full_commits.begin(), full_commits.end());

    // Push information about all known commits to the full list
    for (const auto& [commit, date, _, __] : full_commits) {
        state->add_full_commit(
            commit, state->config->get_commit_period(date));
    }


    for_each_commit(state, full_commits);

    for (auto& [oid, date, commit, _] : full_commits) {
        git::commit_free(commit);
    }

    Vec<SubTaskParams> params;
    LOG_I(state) << "Getting the list of files and commits for code "
                    "origin information ...";
    for (auto bar =
             ScopedBar(state, state->sampled_commits.size(), "commits");
         const auto& [oid, id] : state->sampled_commits) {
        file_tasks(params, state, oid, id);
        bar.tick();
    }

    LOG_I(state) << "Done. Total number of files: " << params.size();

    int index = 0;
    for (auto& param : params) {
        param.index     = index;
        param.max_count = params.size();
        ++index;
    }

    constexpr int                         max_parallel = 32;
    std::counting_semaphore<max_parallel> counting{max_parallel};
    Vec<std::future<FileId>>              walked{};
    for (auto bar = ScopedBar(state, params.size(), "files", true, 40);
         const auto& param : params) {
        bar.tick();
        auto sub_task = [state, param, &counting]() -> FileId {
            finally finish{[&counting]() { counting.release(); }};
            // Walker returns optional analysis result
            auto result = exec_walker(
                param.commit_oid,
                state,
                param.out_commit,
                param.root.c_str(),
                param.entry);

            if (!result.isNil()) {
                // FIXME This sink is placed inside of the `process_filter`
                // tick range, so increasing debugging level would
                // invariably mess up the stdout. It might be possible to
                // introduce a HACK via CLI configuration - disable progres
                // bar if stdout sink shows trace records (after all these
                // two items perform the same task)
                LOG_T(state) << fmt::format(
                    "FILE {:>5}/{:<5} {} {}",
                    param.index,
                    param.max_count,
                    oid_tostr(param.commit_oid),
                    param.root + git::tree_entry_name(param.entry));
            }

            return result;
        };

        counting.acquire();

        switch (state->config->use_threading) {
            case walker_config::async: {
                walked.push_back(std::async(std::launch::async, sub_task));
                break;
            }
            case walker_config::defer: {
                walked.push_back(
                    std::async(std::launch::deferred, sub_task));
                break;
            }
            case walker_config::sequential: {
                auto tmp = sub_task();
                walked.push_back(std::async(
                    std::launch::deferred, [tmp]() { return tmp; }));
                break;
            }
        }
    }

    for (auto& future : walked) {
        future.get();
    }

    LOG_I(state) << "All commits finished";

    for (auto& param : params) {
        git::tree_entry_free(param.entry);
    }

    {
        LOG_I(state) << "Assigning line categories";
        auto& multi       = state->content->multi;
        auto  max_size    = multi.store<LineData>().size();
        auto  line_assign = init_progress(max_size);
        int   count       = 0;
        logging::core::get()->flush();
        for (auto& line : multi.store<LineData>().items()) {
            line->category = state->config->classify_line(
                multi.store<String>().at(line->content).text);

            if (state->config->log_progress_bars) {
                tick_next(line_assign, ++count, max_size, "unqiue lines");
            }
        }
        if (state->config->log_progress_bars) {
            line_assign.mark_as_completed();
        }
    }
    return processed;
}
