#include "cli_options.hpp"

#include <boost/lexical_cast.hpp>

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


void PrintVariableMap(const po::variables_map vm) {
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

po::variables_map parse_cmdline(int argc, const char** argv) {
    po::variables_map                  vm;
    po::options_description            desc{"Options"};
    po::positional_options_description pos{};

    desc.add_options()
        //
        ("help,h", "Help screen") //
        ("logfile",
         po::value<Str>()->default_value("/tmp/git_user.log"),
         "Log file location") //
        ("branch",
         po::value<Str>()->default_value("master"),
         "Repository branch to analyse") //
        ("incremental",
         po::value<BoolOption>()->default_value(
             BoolOption(false), "false"),
         "Load previosly created database and only process commits that "
         "were not registered previously") //
        ("outfile",
         po::value<Str>(),
         "Output file location. If not supplied output will be "
         "generated based on the input repo location")(
            "allowed",
            po::value<Vec<Str>>(),
            "List of globs for allowed paths") //
        ("config",
         po::value<Vec<Str>>(),
         "Config file where options may be specified (can be specified "
         "more than once)") //
        ("log-progress",
         po::value<BoolOption>()->default_value(BoolOption(true), "true"),
         "Show dynamic progress bars for operations") //
        ("blame-subprocess",
         po::value<BoolOption>()->default_value(BoolOption(true), "true"),
         "Use blame for subprocess")                        //
        ("repo", po::value<Str>(), "Input repository path") //
        ("filter-script",
         po::value<Str>(),
         "User-provided python script that configures code forensics "
         "filter")
        //
        ;

    pos.add("repo", 1);

    try {
        store(
            po::command_line_parser(argc, argv)
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

    } catch (const po::error& ex) {
        std::cerr << ex.what() << "\n";
        exit(1);
    }


    return vm;
}

void validate(boost::any& v, const Vec<Str>& xs, BoolOption* opt, long) {
    fmt::print("Provided validation values {}\n", xs);
    if (v.empty()) {
        // I don't know how to assign default here so this works only when
        // default is false
        v = BoolOption(true);
    } else {
        v = BoolOption(boost::lexical_cast<bool>(xs[0]));
    }
}
