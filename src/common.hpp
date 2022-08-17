#pragma once

#include <iostream>
#include <vector>
#include <optional>
#include <functional>
#include <variant>
#include <memory>
#include <string>
#include <cstdint>
#include <experimental/type_traits>

/// Helper implementation to pass multiple types around in a 'pack'
template <typename... Args>
struct arg_pack {};

using Str = std::string;

using i8  = std::int8_t;
using u8  = std::uint8_t;
using i16 = std::int16_t;
using u16 = std::uint16_t;
using i32 = std::int32_t;
using u32 = std::uint32_t;
using i64 = std::int64_t;
using u64 = std::uint64_t;
// clang-format off

template <typename ...Args> using Var = std::vector<Args...>;

template <typename T> using Vec  = std::vector<T>;
template <typename T> using CR   = const T&;
template <typename T> using CP   = const T*;
template <typename T> using P    = T*;
template <typename T> using C    = const T;
template <typename T> using Opt  = std::optional<T>;
template <typename T> using UPtr = std::unique_ptr<T>;
template <typename T> using SPtr = std::shared_ptr<T>;
template <typename T> using Func = std::function<T>;

// clang-format on

struct finally {
    Func<void(void)> action;
    explicit finally(Func<void(void)> _action) : action(_action) {}
    ~finally() { action(); }
};


template <typename T>
std::ostream& operator<<(std::ostream& out, const std::vector<T>& vec) {
    out << "[";
    for (int i = 0; i < vec.size(); ++i) {
        if (0 < i) { out << ", "; }
        out << vec[i];
    }

    out << "]";

    return out;
}


/// Helper type trait to check whether type \param Derived is derived from
/// the \param Base class - including cases when \param Base is an
/// partially specialized type name.
template <template <typename...> class Base, typename Derived>
struct is_base_of_template {
    // A function which can only be called by something convertible to a
    // Base<Ts...>*
    template <typename... Ts>
    static auto constexpr is_callable(Base<Ts...>*) -> arg_pack<Ts...>;

    // Detector, will return type of calling is_callable, or it won't
    // compile if that can't be done
    template <typename T>
    using is_callable_t = decltype(is_callable(std::declval<T*>()));

    // Is it possible to call is_callable which the Derived type
    static inline constexpr bool
        value = std::experimental::is_detected_v<is_callable_t, Derived>;

    // If it is possible to call is_callable with the Derived type what
    // would it return, if not type is a void
    using type = std::experimental::
        detected_or_t<void, is_callable_t, Derived>;
};

template <template <typename...> class Base, typename Derived>
using is_base_of_template_t = typename is_base_of_template<Base, Derived>::
    type;

/// Convenience helper trait for getting `::value` of the trait check
template <template <typename...> class Base, typename Derived>
inline constexpr bool
    is_base_of_template_v = is_base_of_template<Base, Derived>::value;

/// Type trait to check whether provided \param T type is in the \param
/// Pack
template <typename T, typename... Pack>
struct is_in_pack;

template <typename V, typename T0, typename... T>
struct is_in_pack<V, T0, T...> {
    static const bool value = is_in_pack<V, T...>::value;
};

template <typename V, typename... T>
struct is_in_pack<V, V, T...> {
    static const bool value = true;
};

template <typename V>
struct is_in_pack<V> {
    static const bool value = false;
};


/// `::value` accessor for the 'is in pack' type trait
template <typename T, typename... Pack>
inline constexpr bool is_in_pack_v = is_in_pack<T, Pack...>::value;
