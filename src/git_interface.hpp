/// \file git_interface.hpp This file provides helper types and wrappers for the libgit API
#ifndef GIT_INTERFACE_HPP
#define GIT_INTERFACE_HPP

#include <git2.h>
#include "common.hpp"
#include <fmt/core.h>

#include <iostream>


namespace git {
struct exception : public std::exception {
    Str message;
    inline exception(int error, const char* funcname) {
        const git_error* e = git_error_last();
        message            = fmt::format(
            "Error {}/{} while calling {}: {}",
            error,
            funcname,
            e->klass,
            e->message);
    }

    const char* what() const noexcept override { return message.c_str(); }
};
} // namespace git


// NOLINTNEXTLINE
#define __GIT_THROW_EXCEPTION(code, function)                             \
    throw git::exception(code, function);

namespace git {
#include "gitwrap.hpp"
}

auto oid_tostr(git_oid oid) -> Str {
    std::array<char, GIT_OID_HEXSZ + 1> result;
    git_oid_tostr(result.data(), sizeof(result), &oid);
    return Str{result.data(), result.size() - 1};
}

template <>
struct fmt::formatter<git_oid> : fmt::formatter<Str> {
    auto format(CR<git_oid> date, fmt::format_context& ctx) const {
        return fmt::formatter<Str>::format(oid_tostr(date), ctx);
    }
};

void tree_walk(
    const git_tree*                               tree,
    git_treewalk_mode                             mode,
    Func<int(const char*, const git_tree_entry*)> callback) {
    using CB      = decltype(callback);
    CB* allocated = new CB;
    *allocated    = std::move(callback);
    git::tree_walk(
        tree,
        mode,
        [](const char*           root,
           const git_tree_entry* entry,
           void*                 payload) -> int {
            CB* impl = static_cast<CB*>(payload);
            try {
                auto __result = (*impl)(root, entry);
                return __result;
            } catch (...) { throw; }
        },
        allocated);
}

namespace std {
template <>
struct hash<git_oid> {
    auto operator()(const git_oid& it) const -> std::size_t {
        return std::hash<Str>()(
            Str(reinterpret_cast<const char*>(&it.id[0]), sizeof(it.id)));
    }
};
} // namespace std

auto operator==(CR<git_oid> lhs, CR<git_oid> rhs) -> bool {
    return git::oid_cmp(&lhs, &rhs) == 0;
}

#endif // GIT_INTERFACE_HPP
