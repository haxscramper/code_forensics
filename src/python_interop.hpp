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
    py::object   period_mapping;
    py::object   sample_predicate;
    py::object   line_classifier;
    SPtr<Logger> logger;

  public:
    void set_logger(SPtr<Logger> log) { logger = log; }

    void log_info(CR<Str> text) { LOG_I(logger) << text; }
    void log_warning(CR<Str> text) { LOG_W(logger) << text; }
    void log_trace(CR<Str> text) { LOG_T(logger) << text; }
    void log_debug(CR<Str> text) { LOG_D(logger) << text; }
    void log_error(CR<Str> text) { LOG_E(logger) << text; }
    void log_fatal(CR<Str> text) { LOG_F(logger) << text; }

    void set_line_classifier(py::object classifier) {
        line_classifier = classifier;
    }

    void set_path_predicate(py::object predicate) {
        path_predicate = predicate;
    }

    void set_period_mapping(py::object mapping) {
        period_mapping = mapping;
    }

    void set_sample_predicate(py::object predicate) {
        sample_predicate = predicate;
    }

    bool allow_path(CR<Str> path) const {
        if (path_predicate) {
            return py::extract<bool>(path_predicate(path));
        } else {
            return true;
        }
    }

    int get_period(CR<PTime> date) const {
        if (period_mapping) {
            return py::extract<int>(period_mapping(date));
        } else {
            return 0;
        }
    }

    bool allow_sample_at_date(CR<PTime> date, CR<Str> author, CR<Str> id)
        const {
        if (sample_predicate) {
            return py::extract<bool>(sample_predicate(date, author, id));
        } else {
            return true;
        }
    }

    int classify_line(CR<Str> line) const {
        if (line_classifier) {
            return py::extract<int>(line_classifier(line));
        } else {
            return 0;
        }
    }
};

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
                "set_path_predicate",
                &PyForensics::set_path_predicate,
                py::args("predicate"))
            .def(
                "set_period_mapping",
                &PyForensics::set_period_mapping,
                py::args("mapping"))
            .def(
                "set_sample_predicate",
                &PyForensics::set_sample_predicate,
                py::args("predicate"));

    py::object module_level_object = class_creator();
    py::scope().attr("config")     = module_level_object;
}

#endif // PYTHON_INTEROP_HPP
