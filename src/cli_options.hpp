#ifndef CLI_OPTIONS_HPP
#define CLI_OPTIONS_HPP

#include "common.hpp"
#include "program_state.hpp"
#include <boost/program_options.hpp>
#include <boost/describe.hpp>
#include <boost/describe/enum_to_string.hpp>
#include <boost/describe/enum_from_string.hpp>
#include <boost/describe/operators.hpp>
#include <fstream>


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

namespace boost {
template <IsDescribedEnum E>
E lexical_cast(CR<Str> in) {
    E result;
    bd::enum_from_string<E>(in.c_str(), result);
    return result;
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
    v = EnumOption<E>(boost::lexical_cast<E>(xs[0]));
}

po::variables_map parse_cmdline(int argc, const char** argv);


void print_variables_map(std::ostream& out, const po::variables_map vm);

#endif // CLI_OPTIONS_HPP
