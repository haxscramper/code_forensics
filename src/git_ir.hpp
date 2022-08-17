#include <sqlite_orm/sqlite_orm.h>
#include <concepts>
#include <iostream>
#include <filesystem>
#include <unordered_map>


#include "common.hpp"
#include "dod_base.hpp"


using namespace sqlite_orm;

template <dod::IsIdType T>
auto operator<<(std::ostream& stream, T id) -> std::ostream& {
    if (id.isNil()) {
        stream << "NULL";
    } else {
        stream << id.getValue();
    }
    return stream;
}

namespace sqlite_orm {
template <dod::IsIdType T>
struct type_printer<T> : public integer_printer {};

template <dod::IsIdType T>
struct statement_binder<T> {
    auto bind(sqlite3_stmt* stmt, int index, T value) -> int {
        if (value.isNil()) {
            return sqlite3_bind_null(stmt, index);

        } else {
            return statement_binder<typename T::id_base_type>().bind(
                stmt, index, value.getValue());
        }
    }
};

template <dod::IsIdType T>
struct field_printer<T> {
    auto operator()(T t) const -> std::string {
        if (t.isNil()) {
            return "NULL";
        } else {
            return field_printer<typename T::id_base_type>()(t.getValue());
        }
    }
};

template <dod::IsIdType T>
struct row_extractor<T> {
    auto extract(const char* row_value) -> T {
        return T::FromValue(std::stoi(row_value));
    }

    auto extract(sqlite3_stmt* stmt, int columnIndex) -> T {
        return T::FromValue(sqlite3_column_int(stmt, columnIndex));
    }
};
}; // namespace sqlite_orm


namespace ir {

DECL_ID_TYPE(LineData, LineId, std::size_t);
DECL_ID_TYPE(Commit, CommitId, std::size_t);
DECL_ID_TYPE(File, FileId, std::size_t);
DECL_ID_TYPE(Directory, DirectoryId, std::size_t);
DECL_ID_TYPE(String, StringId, std::size_t);

} // namespace ir


namespace dod {
/// Provide struct specialization for string to be able to get it's id
/// type.
template <>
struct id_type<Str> {
    using type = ir::StringId;
};
} // namespace dod

namespace ir {

DECL_ID_TYPE(Author, AuthorId, int);

/// single commit by author, taken at some point in time
struct Commit {
    using id_type = CommitId;
    AuthorId author;   /// references unique author id
    i64      time;     /// posix time
    int      timezone; /// timezone where commit was taken
    Str      hash;     /// git hash of the commit
    int      period; /// Number of the period that commit was attributed to
    Str      message; /// Commit message
    Vec<FileId> files;
};

struct LinePeriods {
    int  begin;
    int  end;
    int  period;
    bool changed;
};

/// single version of the file that appeared in some commit
struct File {
    using id_type = FileId;
    CommitId commit_id; /// Id of the commit this version of the file was
                        /// recorded in
    DirectoryId parent; /// parent directory
    StringId    name;   /// file name
    int         total_complexity; /// Total file complexity
    int         line_count;       /// Total line count for the commit
    bool        had_changes; /// Whether file had any changes in the commit
    Vec<LinePeriods> changed_ranges; ///
    Vec<LineId>      lines; /// List of all lines found in the file
};

/// Single directory path part, without specification at which point in
/// time it existed. Used for the representation of the repository
/// structure.
struct Directory {
    using id_type = DirectoryId;
    Opt<DirectoryId> parent; /// Parent directory ID
    Str              name;   /// Id of the string

    auto operator==(CR<Directory> other) const -> bool {
        return name == other.name && parent == other.parent;
    }
};

/// Table of interned stirngs for different purposes
struct String {
    using id_type = StringId;
    Str  text; /// Textual content of the line
    auto operator==(CR<String> other) const -> bool {
        return text == other.text;
    }
};

/// Author - name and email found during the source code analysis.
struct Author {
    using id_type = AuthorId;
    Str name;
    Str email;

    auto operator==(CR<Author> other) const -> bool {
        return name == other.name && email == other.email;
    }
};


/// Single line in a file with all the information that can be relevang for
/// the further analysis. Provides information about the /content/ found at
/// some line. Interned in the main storage.
struct LineData {
    using id_type = LineId;
    AuthorId author;   /// Line author ID
    i64      time;     /// Time line was written
    StringId content;  /// Content of the line
    int      nesting;  /// Line indentation depth
    int      category; /// Line category

    auto operator==(CR<LineData> other) const -> bool {
        return author == other.author && time == other.time &&
               content == other.content;
    }
};
} // namespace ir


// Taken from the SO answer
// https://stackoverflow.com/questions/2590677/how-do-i-combine-hash-values-in-c0x
inline void hash_combine(std::size_t& seed) {}

template <typename T, typename... Rest>
inline void hash_combine(std::size_t& seed, const T& v, Rest... rest) {
    std::hash<T> hasher;
    seed ^= hasher(v) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
    hash_combine(seed, rest...);
}

#define MAKE_HASHABLE(__type, __varname, ...)                             \
    namespace std {                                                       \
        template <>                                                       \
        struct hash<__type> {                                             \
            auto operator()(const __type& __varname) const                \
                -> std::size_t {                                          \
                std::size_t ret = 0;                                      \
                hash_combine(ret, __VA_ARGS__);                           \
                return ret;                                               \
            }                                                             \
        };                                                                \
    }

// Add hashing declarations for the author and line data - they will be
// interned. `std::string` already has the hash structure.
MAKE_HASHABLE(ir::Author, it, it.name, it.email);
MAKE_HASHABLE(ir::LineData, it, it.author, it.time, it.content);
MAKE_HASHABLE(ir::Directory, it, it.name, it.parent);
MAKE_HASHABLE(ir::String, it, it.text);

using Path = std::filesystem::path;

namespace ir {
struct content_manager {
    dod::MultiStore<
        dod::InternStore<AuthorId, Author>, // Full list of authors
        dod::InternStore<LineId, LineData>, // found lines
        dod::Store<FileId, File>,           // files
        dod::Store<CommitId, Commit>,       // all commits
        dod::Store<DirectoryId, Directory>, // all directories
        dod::InternStore<StringId, String>  // all interned strings
        >
        multi;

    std::unordered_map<Str, DirectoryId> prefixes;

    auto parentDirectory(CR<Path> dir) -> Opt<DirectoryId> {
        if (dir.has_parent_path()) {
            auto parent = dir.parent_path();
            auto native = parent.native();
            if (prefixes.contains(native)) {
                return prefixes.at(native);
            } else {
                auto result = getDirectory(parent);
                prefixes.insert({parent, result});
                return result;
            }
        } else {
            return Opt<DirectoryId>{};
        }
    }

    auto getDirectory(CR<Path> dir) -> DirectoryId {
        return add(ir::Directory{
            .parent = parentDirectory(dir), .name = dir.native()});
    }

    /// Get reference to value pointed to by the ID
    template <dod::IsIdType Id>
    auto at(Id id) -> typename dod::value_type_t<Id>& {
        return multi.at<Id>(id);
    }

    /// Push in a value, return newly generated ID
    template <typename T>
    [[nodiscard]] auto add(CR<T> it) -> dod::id_type_t<T> {
        return multi.add<T>(it);
    }
};


/// Intermediate types for the ORM storage - they are used in order to
/// provide interfacing - `id` field and default constructors (for the
/// `iterate<>()` method in the storage)

struct orm_file : File {
    FileId id;
    orm_file()
        : File{.commit_id = CommitId::Nil(), .parent = DirectoryId::Nil(), .name = StringId::Nil()}
        , id(FileId::Nil()) {}
    orm_file(FileId _id, CR<File> base) : File(base), id(_id) {}
};

struct orm_commit : Commit {
    CommitId id;

    orm_commit()
        : Commit{.author = AuthorId::Nil()}, id(CommitId::Nil()) {}
    orm_commit(CommitId _id, CR<Commit> base) : Commit(base), id(_id) {}
};

struct orm_dir : Directory {
    DirectoryId id;

    orm_dir() : Directory{}, id(DirectoryId::Nil()) {}
    orm_dir(DirectoryId _id, CR<Directory> base)
        : Directory(base), id(_id) {}
};

struct orm_string : String {
    StringId id;

    orm_string() : String{}, id(StringId::Nil()) {}
    orm_string(StringId _id, CR<String> base) : String(base), id(_id) {}
};

struct orm_author : Author {
    AuthorId id;


    orm_author() : Author{}, id(AuthorId::Nil()) {}
    orm_author(AuthorId _id, CR<Author> base) : Author(base), id(_id) {}
};

struct orm_line : LineData {
    LineId id;
    orm_line()
        : LineData{.author = AuthorId::Nil(), .content = StringId::Nil()}
        , id(LineId::Nil()) {}

    orm_line(LineId _id, CR<LineData> base) : LineData(base), id(_id) {}
};

struct orm_lines_table {
    FileId file;
    int    index;
    LineId line;
};

struct orm_changed_range : LinePeriods {
    FileId file;
    int    index;
};

auto create_db(CR<Str> storagePath) {
    auto storage = make_storage(
        storagePath,
        make_table<orm_commit>(
            "commits",
            make_column("id", &orm_commit::id, primary_key()),
            make_column("author", &orm_commit::author),
            make_column("time", &orm_commit::time),
            make_column("hash", &orm_commit::hash),
            make_column("period", &orm_commit::period),
            make_column("timezone", &orm_commit::timezone),
            make_column("message", &orm_commit::message)),
        make_table<orm_file>(
            "file",
            make_column("id", &orm_file::id, primary_key()),
            make_column("commit_id", &orm_file::commit_id),
            make_column("name", &orm_file::name),
            make_column("line_count", &orm_file::line_count),
            make_column("total_complexity", &orm_file::total_complexity),
            make_column("had_changes", &orm_file::had_changes)),
        make_table<orm_author>(
            "author",
            make_column("id", &orm_author::id, primary_key()),
            make_column("name", &orm_author::name),
            make_column("email", &orm_author::email)),
        make_table<orm_line>(
            "line",
            make_column("id", &orm_line::id, primary_key()),
            make_column("author", &orm_line::author),
            make_column("time", &orm_line::time),
            make_column("content", &orm_line::content),
            make_column("category", &orm_line::category),
            make_column("nesting", &orm_line::nesting)),
        make_table<orm_lines_table>(
            "file_lines",
            make_column("file", &orm_lines_table::file),
            make_column("index", &orm_lines_table::index),
            make_column("line", &orm_lines_table::line)),
        make_table<orm_changed_range>(
            "changed_ranges",
            make_column("file", &orm_changed_range::file),
            make_column("index", &orm_changed_range::index),
            make_column("begin", &orm_changed_range::begin),
            make_column("end", &orm_changed_range::end),
            make_column("period", &orm_changed_range::period),
            make_column("changed", &orm_changed_range::changed)),
        make_table<orm_dir>(
            "dir",
            make_column("id", &orm_dir::id, primary_key()),
            make_column("parent", &orm_dir::parent),
            make_column("name", &orm_dir::name)),
        make_table<orm_string>(
            "strings",
            make_column("id", &orm_string::id, primary_key()),
            make_column("text", &orm_string::text)));

    return storage;
}

using DbConnection = decltype(create_db(""));

} // namespace ir
