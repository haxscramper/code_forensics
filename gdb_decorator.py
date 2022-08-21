import gdb
import re
import pprint
from typing import Iterator, Text

# Partially based on the https://github.com/daskol/gdb-colour-filter/blob/master/colour_filter.py


class UserFrameDecorator(gdb.FrameDecorator.FrameDecorator):
    def __init__(self, fobj):
        super(CommonAliasDecorator, self).__init__(fobj)

    def __init__(self, *args, depth=0, **kwargs):
        super(UserFrameDecorator, self).__init__(*args, **kwargs)

        self._depth = depth
        self.frame = super(UserFrameDecorator, self).inferior_frame()

    def __str__(self):
        is_print_address = gdb.parameter("print address")

        part1 = self.depth()
        part2 = self.function() + " \033[1;37m(" + self.frame_args() + ")\033[0m"
        part3 = self.filename() + self.line()

        if is_print_address:
            part1 += "  " + self.address() + " in "
        else:
            part1 += " "

        parts = part1 + part2 + "\n at " + part3

        screen_width = self.get_screen_width()
        if screen_width is not None and len(parts) > screen_width:
            shift_width = int(self.length(part1)) - 1
            shift_width -= 3 * int(is_print_address)  # compensate ' in ' part
            value = part1 + part2 + "\n"
            value += " " * shift_width + " at " + part3
        else:
            value = parts

        return value

    def address(self) -> str:
        address = super(UserFrameDecorator, self).address()
        return "\033[1;30m0x%016x\033[0m" % address

    def depth(self) -> str:
        return "\033[1;37m#%-3d\033[0m" % self._depth

    def filename(self) -> str:
        filename = super(UserFrameDecorator, self).filename()
        return "\033[0;36m%s\033[0m" % filename

    def frame_args(self) -> str:
        return ""

        try:
            block = self.frame.block()
        except RuntimeError:
            block = None

        while block is not None:
            if block.function is not None:
                break
            block = block.superblock

        if block is None:
            return ""

        args = []

        for sym in block:
            if not sym.is_argument:
                continue
            val = sym.value(self.frame)
            arg = "%s=%s" % (sym, val) if str(val) else str(sym)
            args.append(arg)

        return ", ".join(args)

    def function(self):
        func = super(UserFrameDecorator, self).function()

        name = func
        # GDB could somehow resolve function name by its address.
        # See details here https://cygwin.com/ml/gdb/2017-12/msg00013.html
        if isinstance(func, int):
            # Here we have something like
            # > raise + 272 in section .text of /usr/lib/libc.so.6
            # XXX: gdb.find_pc_line
            symbol = gdb.execute("info symbol 0x%016x" % func, False, True)

            # But here we truncate layout in binary
            # > raise + 272
            sym_name = symbol[: symbol.find("in section")].strip()

            # Check if we in format
            # > smthing + offset
            parts = sym_name.rsplit(" ", 1)
            # > raise
            if len(parts) == 1:
                name = sym_name

            try:
                name = parts[0] + " " + hex(int(parts[1]))

            except ValueError:
                name = sym_name

        # FIXME HACK this approach is error-prone. Instead all convesions
        # should be done using tree-sitter - python has general wrappers,
        # but I need to compile/configure each language separately, so for
        # now I will use this, it is "good enough (TM)"
        #
        # Better approach would be to parse the whole structure of the
        # input procedure, /maybe/ also parse project configuration (or
        # provide helper script to populate the rename table) and merge
        # them together.
        for (namespace, alias) in [
            ("boost::python", "py"),
            ("boost::posix_time::ptime", "PTime"),
            ("boost::program_options", "po"),
            ("std::vector", "Vec"),
            ("std::__cxx11::basic_string<char>", "Str"),
            ("std::__cxx11::basic_string<char, *std::char_traits<char>>", "Str"),
            (
                "std::__cxx11::basic_string<char, *std::char_traits<char>, *std::allocator<char> *>",
                "Str",
            ),
            # NOTE yes, I know this is terrible, but if function accepts
            # const reference most likely there won't be overload that also
            # copes or mutates things in-place.
            (" *const&", ""),
            # 'const' method annotations
            (r"\) const", ")"),
            (r", std::allocator<.*?> *", ""),
            # Old-style template parameter spacing - really distracting
            (" +>", ">"),
            # Trailing in-function offset
            (r"\) \+ 0x\d+", ")"),
        ]:
            name = re.sub(namespace, alias, name)

        return "\033[1;34m" + name + "\033[0m"

    def get_screen_width(self):
        """Get screen width from GDB. Source format is following"""
        return gdb.parameter("width")

    def line(self):
        value = super(UserFrameDecorator, self).line()
        return "\033[0;35m:%d\033[0m" % value if value else ""

    @staticmethod
    def length(colored_string):
        """This function calculates length of string with terminal control
        sequences.
        """
        start = 0
        term_seq_len = 0

        while True:
            begin = colored_string.find("\033", start)

            if begin == -1:
                break

            end = colored_string.find("m", begin)

            if end == -1:
                end = len(s)

            term_seq_len += end - begin + 1
            start = end

        return len(colored_string) - term_seq_len


class FilterProxy:
    """FilterProxy class keep ensures that frame iterator will be comsumed
    properly on the first and the sole call.
    """

    def __init__(self, frames: Iterator[gdb.Frame]):
        self.frames = (
            UserFrameDecorator(frame, depth=ix) for ix, frame in enumerate(frames)
        )

    def __iter__(self):
        return self

    def __next__(self):
        self.unroll_stack()
        raise StopIteration

    def unroll_stack(self):
        output = (str(frame) for frame in self.frames)
        print("\n".join(output))


class UserFilter:
    def __init__(self):
        # set required attributes
        self.name = "UserFilter"
        self.enabled = True
        self.priority = 0

        # register with current program space
        gdb.current_progspace().frame_filters[self.name] = self

    def filter(self, frame_iter: Iterator[gdb.Frame]) -> Iterator[gdb.Frame]:
        return FilterProxy(frame_iter)


UserFilter()
