/// \file python_interop.hpp \brief Python module definition and
/// interfacing classes

#ifndef PYTHON_INTEROP_HPP
#define PYTHON_INTEROP_HPP

#include "common.hpp"
#include "logging.hpp"


#include <boost/python.hpp>

// Python datetime header file
#include <datetime.h>

namespace py = boost::python;

class PyForensics {
    py::object   path_predicate;
    py::object   commit_period_mapping;
    py::object   sample_period_mapping;
    py::object   sample_predicate;
    py::object   line_classifier;
    py::object   post_analyze;
    SPtr<Logger> logger;

  public:
    void set_logger(SPtr<Logger> log) { logger = log; }

    /// \brief write text as a info-level log record
    void log_info(CR<Str> text) { LOG_I(logger) << text; }
    /// \brief write text as a warning-level log record
    void log_warning(CR<Str> text) { LOG_W(logger) << text; }
    /// \brief write text as a trace-level log record
    void log_trace(CR<Str> text) { LOG_T(logger) << text; }
    /// \brief write text as a debug-level log record
    void log_debug(CR<Str> text) { LOG_D(logger) << text; }
    /// \brief write text as a error-level log record
    void log_error(CR<Str> text) { LOG_E(logger) << text; }
    /// \brief write text as a fatal-level log record
    void log_fatal(CR<Str> text) { LOG_F(logger) << text; }


    /// \brief set post-analyze hook implementation
    void set_post_analyze(py::object post) { post_analyze = post; }

    /// \brief set line classification callback for the #classify_line
    void set_line_classifier(py::object classifier) {
        line_classifier = classifier;
    }

    /// \brief set path filtering predicate for the #allow_path predicate
    void set_path_predicate(py::object predicate) {
        path_predicate = predicate;
    }

    /// \brief set period mapping callback for the #get_commit_period
    void set_commit_period_mapping(py::object mapping) {
        commit_period_mapping = mapping;
    }

    /// \brief set period mapping callback for the #get_sample_period
    void set_sample_period_mapping(py::object mapping) {
        sample_period_mapping = mapping;
    }

    /// \brief set sample predicate callback for the #allow_sample_at_date predicate
    void set_sample_predicate(py::object predicate) {
        sample_predicate = predicate;
    }


    /// \brief Check whether provided path should be processed for the
    /// 'blame' information
    bool allow_path(CR<Str> path) const {
        if (path_predicate) {
            return py::extract<bool>(path_predicate(path));
        } else {
            return true;
        }
    }

    /// \brief Get period number from the specified commit date
    int get_commit_period(CR<PTime> date) const {
        if (commit_period_mapping) {
            return py::extract<int>(commit_period_mapping(date));
        } else {
            return 0;
        }
    }


    /// \brief Get period number from the specified commit date
    int get_sample_period(CR<PTime> date) const {
        if (sample_period_mapping) {
            return py::extract<int>(sample_period_mapping(date));
        } else {
            return 0;
        }
    }

    /// \brief Check whether commit by \arg author at a \arg date should be
    /// sampled for the blame info
    bool allow_sample_at_date(CR<PTime> date, CR<Str> author, CR<Str> id)
        const {
        if (sample_predicate) {
            return py::extract<bool>(sample_predicate(date, author, id));
        } else {
            return true;
        }
    }

    /// \brief get line category
    int classify_line(CR<Str> line) const {
        if (line_classifier) {
            return py::extract<int>(line_classifier(line));
        } else {
            return 0;
        }
    }

    void run_post_analyze() const {
        if (post_analyze) { post_analyze(); }
    }
};


/// \brief helper type to aid conversion from input type T to the python
/// object
template <typename T>
struct type_into_python {
    static PyObject* convert(T const&);
};

template <typename T>
struct type_from_python {
    type_from_python() {
        py::converter::registry::push_back(
            convertible, construct, py::type_id<T>());
    }

    static void* convertible(PyObject* obj);

    static void construct(
        PyObject*                                      obj,
        py::converter::rvalue_from_python_stage1_data* data);
};

/// {@
/// Template specialization for python-C++ type conversion
template <>
PyObject* type_into_python<PTime>::convert(CR<PTime> t) {
    auto d    = t.date();
    auto tod  = t.time_of_day();
    auto usec = tod.total_microseconds() % 1000000;
    return PyDateTime_FromDateAndTime(
        d.year(),
        d.month(),
        d.day(),
        tod.hours(),
        tod.minutes(),
        tod.seconds(),
        usec);
}

template <>
void* type_from_python<PTime>::convertible(PyObject* obj) {
    return PyDateTime_Check(obj) ? obj : nullptr;
}

template <>
void type_from_python<PTime>::construct(
    PyObject*                                      obj,
    py::converter::rvalue_from_python_stage1_data* data) {
    auto storage = reinterpret_cast<
                       py::converter::rvalue_from_python_storage<PTime>*>(
                       data)
                       ->storage.bytes;
    Date date_only(
        PyDateTime_GET_YEAR(obj),
        PyDateTime_GET_MONTH(obj),
        PyDateTime_GET_DAY(obj));
    TimeDuration time_of_day(
        PyDateTime_DATE_GET_HOUR(obj),
        PyDateTime_DATE_GET_MINUTE(obj),
        PyDateTime_DATE_GET_SECOND(obj));
    time_of_day += boost::posix_time::microsec(
        PyDateTime_DATE_GET_MICROSECOND(obj));
    new (storage) PTime(date_only, time_of_day);
    data->convertible = storage;
}
/// @}

template <>
PyObject* type_into_python<Date>::convert(Date const& d) {
    return PyDate_FromDate(d.year(), d.month(), d.day());
}

template <>
void* type_from_python<Date>::convertible(PyObject* obj) {
    return PyDate_Check(obj) ? obj : nullptr;
}

template <>
void type_from_python<Date>::construct(
    PyObject*                                      obj,
    py::converter::rvalue_from_python_stage1_data* data) {
    auto storage = reinterpret_cast<
                       py::converter::rvalue_from_python_storage<Date>*>(
                       data)
                       ->storage.bytes;
    new (storage) Date(
        PyDateTime_GET_YEAR(obj),
        PyDateTime_GET_MONTH(obj),
        PyDateTime_GET_DAY(obj));
    data->convertible = storage;
}


BOOST_PYTHON_MODULE(forensics) {
    PyDateTime_IMPORT;

    py::to_python_converter<PTime, type_into_python<PTime>>();
    type_from_python<PTime>();

    py::to_python_converter<Date, type_into_python<Date>>();
    type_from_python<Date>();

    py::object class_creator =
        //
        py::class_<PyForensics>("Forensics") //
            .def("log_info", &PyForensics::log_info, py::args("text"))
            .def(
                "log_warning", &PyForensics::log_warning, py::args("text"))
            .def("log_trace", &PyForensics::log_trace, py::args("text"))
            .def("log_debug", &PyForensics::log_debug, py::args("text"))
            .def("log_error", &PyForensics::log_error, py::args("text"))
            .def("log_fatal", &PyForensics::log_fatal, py::args("text"))
            .def(
                "set_line_classifier",
                &PyForensics::set_line_classifier,
                py::args("classifier"))
            .def(
                "set_post_analyze",
                &PyForensics::set_post_analyze,
                py::arg("post"))
            .def(
                "set_path_predicate",
                &PyForensics::set_path_predicate,
                py::args("predicate"))
            .def(
                "set_commit_period_mapping",
                &PyForensics::set_commit_period_mapping,
                py::args("mapping"))
            .def(
                "set_sample_period_mapping",
                &PyForensics::set_sample_period_mapping,
                py::args("mapping"))
            .def(
                "set_sample_predicate",
                &PyForensics::set_sample_predicate,
                py::args("predicate"));

    py::object module_level_object = class_creator();
    py::scope().attr("config")     = module_level_object;
}

#endif // PYTHON_INTEROP_HPP
