#include "cli_options.hpp"

#include <boost/lexical_cast.hpp>
#include <locale>
#include <cstdlib>

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

template <>
BoolOption lexical_cast<BoolOption, Str>(CR<Str> arg) {
    return BoolOption(lexical_cast<bool, Str>(arg));
}

template <>
Str lexical_cast<Str, BoolOption>(CR<BoolOption> b) {
    return lexical_cast<Str, bool>(b.getState());
}
} // namespace boost


void print_variables_map(
    CR<any_visitor>         visitor,
    std::ostream&           out,
    const po::variables_map vm) {
    for (auto& it : vm) {
        out << "> " << it.first;
        auto val = it.second.value();
        if (((boost::any)val).empty()) { out << "(empty)"; }
        if (vm[it.first].defaulted() || it.second.defaulted()) {
            out << "(default)";
        }
        out << "=";
        if (visitor(val)) {
            out << "\n";
            continue;
        }

        bool is_char;
        try {
            boost::any_cast<const char*>(val);
            is_char = true;
        } catch (const boost::bad_any_cast&) { is_char = false; }
        bool is_str;
        try {
            boost::any_cast<Str>(val);
            is_str = true;
        } catch (const boost::bad_any_cast&) { is_str = false; }

        if (((boost::any)val).type() == typeid(int)) {
            out << vm[it.first].as<int>() << std::endl;
        } else if (((boost::any)val).type() == typeid(bool)) {
            out << vm[it.first].as<bool>() << std::endl;
        } else if (((boost::any)val).type() == typeid(BoolOption)) {
            out << std::boolalpha << vm[it.first].as<BoolOption>()
                << std::endl;
        } else if (((boost::any)val).type() == typeid(double)) {
            out << vm[it.first].as<double>() << std::endl;
        } else if (is_char) {
            out << vm[it.first].as<const char*>() << std::endl;
        } else if (is_str) {
            Str temp = vm[it.first].as<Str>();
            if (temp.size()) {
                out << temp << std::endl;
            } else {
                out << "true" << std::endl;
            }
        } else { // Assumes that the only remainder is vector<string>
            try {
                Vec<Str> vect = vm[it.first].as<Vec<Str>>();
                uint     i    = 0;
                for (Vec<Str>::iterator oit = vect.begin();
                     oit != vect.end();
                     oit++, ++i) {
                    out << "\r> " << it.first << "[" << i << "]=" << (*oit)
                        << std::endl;
                }
            } catch (const boost::bad_any_cast&) {
                out << "UnknownType(" << ((boost::any)val).type().name()
                    << ")" << std::endl;
            }
        }
    }
}

template <typename T>
T cast_env_or(CR<Str> env, CR<T> or_value) {
    const char* value = std::getenv(env.c_str());
    if (value == nullptr) {
        return or_value;
    } else {
        return boost::lexical_cast<T>(Str{value});
    }
}

template <typename T>
T map_env(CR<Str> env, Func<T(CR<Str>)> callback) {
    const char* value = std::getenv(env.c_str());
    if (value == nullptr) {
        return callback("");
    } else {
        return callback(Str{value});
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
         po::value<BoolOption>()->default_value(
             BoolOption(map_env<bool>(
                 "CI",
                 [](CR<Str> value) {
                     if (value.empty()) {
                         return true;
                     } else {
                         return false;
                     }
                 })),
             "$CI or 'true'"),
         "Show dynamic progress bars for operations") //
        ("blame-subprocess",
         po::value<BoolOption>()->default_value(BoolOption(true), "true"),
         "Use blame for subprocess")                        //
        ("repo", po::value<Str>(), "Input repository path") //
        ("filter-script",
         po::value<Str>(),
         "User-provided python script that configures code forensics "
         "filter") //
        ("analytics",
         po::value<Vec<EnumOption<Analytics>>>()->default_value(
             Vec<EnumOption<Analytics>>(), "all"),
         "Which group of analytics to enable (default- all)") //
        ("filter-args",
         po::value<Vec<Str>>(),
         "command line arguments to the filter script")
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
    v = BoolOption(boost::lexical_cast<bool>(xs[0]));
}
