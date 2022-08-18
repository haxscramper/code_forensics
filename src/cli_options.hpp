#ifndef CLI_OPTIONS_HPP
#define CLI_OPTIONS_HPP

#include "common.hpp"
#include <boost/program_options.hpp>
#include <fstream>


namespace po = boost::program_options;

// https://stackoverflow.com/questions/51723237/boostprogram-options-bool-switch-used-multiple-times
// bool options is taken from this SO question - it is not /exactly/ what I
// aimed for, but this solution allows specifying =true or =false on the
// command line explicitly, which I aimed for

class BoolOption {
  public:
    inline BoolOption(bool initialState = false) : state(initialState) {}
    inline bool getState() const { return state; }
    inline void switchState() { state = !state; }
                operator bool() const { return state; }

  private:
    bool state;
};


void validate(boost::any& v, Vec<Str> const& xs, BoolOption* opt, long);


po::variables_map parse_cmdline(int argc, const char** argv);


// inline void PrintUsage(const options_description desc) {
//     std::cout << "Usage: " << app_name << " [options]" << std::endl;
//     std::cout << "    App description" << std::endl;
//     std::cout << desc << std::endl;
//     std::cout << std::endl << "v" << VERSION << std::endl;
// }

void print_variables_map(std::ostream& out, const po::variables_map vm);

#endif // CLI_OPTIONS_HPP
