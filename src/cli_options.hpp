#ifndef CLI_OPTIONS_HPP
#define CLI_OPTIONS_HPP

#include <common.hpp>
#include "program_state.hpp"
#include <boost/program_options.hpp>
#include <boost/describe.hpp>
#include <boost/describe/enum_to_string.hpp>
#include <boost/describe/enum_from_string.hpp>
#include <boost/describe/operators.hpp>
#include <boost/function.hpp>
#include <boost/bind.hpp>
#include <boost/lambda/lambda.hpp>
#include <boost/unordered_map.hpp>
#include <fstream>

/// Has typeinfo information for type-implementation mapping
struct type_info_hash {
    std::size_t operator()(std::type_info const& t) const {
        return t.hash_code();
    }
};

/// Compare reference wrappers for equality
struct equal_ref {
    template <typename T>
    bool operator()(
        boost::reference_wrapper<T> a,
        boost::reference_wrapper<T> b) const {
        return a.get() == b.get();
    }
};


/// \brief `boost::any` visitor helper
struct any_visitor {
    boost::unordered_map<
        boost::reference_wrapper<std::type_info const>,
        boost::function<void(boost::any&)>,
        type_info_hash,
        equal_ref>
        fs;

    /// \brief Convert 'any' value to specified type
    template <typename T>
    static T any_cast_f(boost::any& any) {
        return boost::any_cast<T>(any);
    }

    /// \brief add visitor for the specified mapping
    template <typename T>
    void insert_visitor(boost::function<void(T)> f) {
        try {
            fs.insert(std::make_pair(
                boost::ref(typeid(T)),
                boost::bind(
                    f, boost::bind(any_cast_f<T>, boost::lambda::_1))));
        } catch (boost::bad_any_cast& e) {
            std::cout << e.what() << std::endl;
        }
    }

    /// \brief try to call any of the stored oeprators with provided \arg
    /// x. Return \return 'true' if call have been made, otherwise return
    /// false.
    inline bool operator()(boost::any& x) const {
        auto it = fs.find(boost::ref(x.type()));
        if (it != fs.end()) {
            it->second(x);
            return true;
        } else {
            return false;
        }
    }
};

namespace po = boost::program_options;

/// \brief enum
template <IsDescribedEnum E>
class EnumOption {
  public:
    EnumOption(E in) : value(in) {}

    inline E get() const noexcept { return value; }

  private:
    E value;

    BOOST_DESCRIBE_CLASS(EnumOption, (), (value), (), ());
};

/// \breif more informative lexical cast error
///
/// Derived from the regular validation error and only providing support
/// for additional mismatch description
class bad_lexical_cast : public boost::bad_lexical_cast {
    Str msg;

  public:
    inline bad_lexical_cast(
        CR<std::type_info> S,
        CR<std::type_info> T,
        CR<Str>            _msg)
        : boost::bad_lexical_cast(S, T), msg(_msg) {}
    inline const char* what() const noexcept override {
        // TODO use cxxabi and write out proper type conversion error
        // message information - not only user-provided failure text
        return strdup((msg).c_str());
    }

    template <typename S, typename T>
    static bad_lexical_cast init(CR<Str> msg) {
        return bad_lexical_cast(typeid(S), typeid(T), msg);
    }
};

/// \brief more informative validation error exception
///
/// Derived from the regular validation error and only providing support
/// for the user-provided error elaboration.
class validation_error : public po::validation_error {
    Str msg; ///< Stored user message

  public:
    /// \brief create validation error with 'invalid option' state
    inline validation_error(Str _msg)
        : po::validation_error(po::validation_error::invalid_option)
        , msg(_msg) {}
    /// \brief get error message description, returning baseline one
    /// concatenated with the user-provdede elaboration
    inline const char* what() const noexcept override {
        return strdup(
            (Str{po::validation_error::what()} + ": " + msg).c_str());
    }
};

namespace boost {
/// \brief lexical cast overload for 'described' enums
template <IsDescribedEnum E>
E lexical_cast(CR<Str> in) {
    E result;
    if (bd::enum_from_string<E>(in.c_str(), result)) {
        return result;
    } else {
        throw ::bad_lexical_cast::init<Str, E>(
            std::string("Invalid enumerator name '") + in +
            "' for enum type '" + typeid(E).name() + "'");
    }
}

/// \brief Lexical cast overload for the 'described' enum values
template <IsDescribedEnum E>
Str lexical_cast(E in) {
    return Str{bd::enum_to_string<E>(in)};
}
} // namespace boost

/// \brief unparse input enum option into the stored value
template <typename E>
void validate(boost::any& v, CR<Vec<Str>> xs, EnumOption<E>* opt, long) {}

/// \brief specify boolean true/false flags on the boost command line
class BoolOption {
    // https://stackoverflow.com/questions/51723237/boostprogram-options-bool-switch-used-multiple-times
    // bool options is taken from this SO question - it is not /exactly/
    // what I aimed for, but this solution allows specifying =true or
    // =false on the command line explicitly, which I aimed for
  public:
    inline BoolOption(bool initialState = false) : state(initialState) {}
    inline bool getState() const { return state; }
    /// \brief toggle stored state
    inline void switchState() { state = !state; }
    /// \brief boolean conversion operator for seamless interoperability
    /// with the regular boolean types
    operator bool() const { return state; }

  private:
    bool state;
};


/// \brief parse enum-valued CLI option
template <IsDescribedEnum E>
void validate(boost::any& v, CR<Vec<Str>> xs, EnumOption<E>*, long) {
    try {
        v = EnumOption<E>(boost::lexical_cast<E>(xs[0]));
    } catch (CR<boost::bad_lexical_cast> err) {
        throw validation_error(err.what());
    }
}

po::variables_map parse_cmdline(int argc, const char** argv);


void print_variables_map(
    CR<any_visitor>         visitor,
    std::ostream&           out,
    const po::variables_map vm);

#endif // CLI_OPTIONS_HPP
