#ifndef CLI_OPTIONS_HPP
#define CLI_OPTIONS_HPP

#include "common.hpp"
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

struct type_info_hash {
    std::size_t operator()(std::type_info const& t) const {
        return t.hash_code();
    }
};

struct equal_ref {
    template <typename T>
    bool operator()(
        boost::reference_wrapper<T> a,
        boost::reference_wrapper<T> b) const {
        return a.get() == b.get();
    }
};

struct any_visitor {
    boost::unordered_map<
        boost::reference_wrapper<std::type_info const>,
        boost::function<void(boost::any&)>,
        type_info_hash,
        equal_ref>
        fs;

    template <typename T>
    static T any_cast_f(boost::any& any) {
        return boost::any_cast<T>(any);
    }

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

// https://stackoverflow.com/questions/51723237/boostprogram-options-bool-switch-used-multiple-times
// bool options is taken from this SO question - it is not /exactly/ what I
// aimed for, but this solution allows specifying =true or =false on the
// command line explicitly, which I aimed for

template <IsDescribedEnum E>
class EnumOption {
  public:
    EnumOption(E in) : value(in) {}

    inline E get() const noexcept { return value; }

  private:
    E value;

    BOOST_DESCRIBE_CLASS(EnumOption, (), (value), (), ());
};

class bad_lexical_cast : public boost::bad_lexical_cast {
    Str msg;

  public:
    inline bad_lexical_cast(
        CR<std::type_info> S,
        CR<std::type_info> T,
        CR<Str>            _msg)
        : boost::bad_lexical_cast(S, T), msg(_msg) {}
    inline const char* what() const noexcept override {
        return strdup((msg).c_str());
    }

    template <typename S, typename T>
    static bad_lexical_cast init(CR<Str> msg) {
        return bad_lexical_cast(typeid(S), typeid(T), msg);
    }
};

class validation_error : public po::validation_error {
    Str msg;

  public:
    inline validation_error(Str _msg)
        : po::validation_error(po::validation_error::invalid_option)
        , msg(_msg) {}
    inline const char* what() const noexcept override {
        return strdup(
            (Str{po::validation_error::what()} + ": " + msg).c_str());
    }
};

namespace boost {
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

template <IsDescribedEnum E>
Str lexical_cast(E in) {
    return Str{bd::enum_to_string<E>(in)};
}
} // namespace boost

template <typename E>
void validate(boost::any& v, CR<Vec<Str>> xs, EnumOption<E>* opt, long) {}

class BoolOption {
  public:
    inline BoolOption(bool initialState = false) : state(initialState) {}
    inline bool getState() const { return state; }
    inline void switchState() { state = !state; }
                operator bool() const { return state; }

  private:
    bool state;
};


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
