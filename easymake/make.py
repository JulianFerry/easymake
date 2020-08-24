import re
import json
import inspect
import argparse

from textwrap import wrap
from tabulate import tabulate


class Makefile:
    """
    Run a Makefile.py script with the same logic as a Makefile

    The Makefile class parses all ``easymake`` command arguments and
    matches them to target functions specified in the user's
    *Makefile.py* with the ``@easymake.target`` decorator.

    - Function arguments should be passed as keyword arguments of the
    form: ``arg=value``.
    - Boolean flags should be passed as command-line flags of the form
    ``-flag``.

    Under the hood, calling ``easymake`` or ``python -m easymake``
    first creates a Makefile object. The user's ``Makefile.py`` module
    is then loaded, in which any @target decorator calls append the
    function to the Makefile object. Finally, the Makefile object's
    ``make()`` command is called, which parses the ``easymake``
    commmand-line arguments and runs all functions specified, using the
    corresponding arguments.

    """
    def __init__(self):
        self.targets = {}

    def add_target(self, function):
        self.targets[function.__name__] = function

    def add_help(self):
        """Add help target to the ezmake file"""
        def shorten(s, n=20):
            if len(s) > n:
                s = s[:n] + '...'
            return s
        def makefile_help(v=False):
            """Print Makefile help based on Makefile docstrings"""
            docs = []
            for name, function in list(self.targets.items())[:-1]:
                # Parse function parameters
                params = inspect.signature(function).parameters.items()
                params = '\n'.join([shorten(str(p[1])) for p in params])
                # Parse docstring
                docstring = function.__doc__ if function.__doc__ else ''
                if not v:
                    docstring = docstring.strip('\n').split('\n')[0]
                docstring = docstring.split('\n')
                docstring = ['\n'.join(wrap(s, width=72)) for s in docstring]
                docstring = '\n'.join(docstring)
                # Append to table
                docs.append((name, params, docstring))
            print(tabulate(
                docs,
                headers=('Target', 'Parameters', 'Docstring'),
                tablefmt='grid'
            ))
        self.targets['help'] = makefile_help

    def make(self):
        self.add_help()
        self._parse_args()
        self._parse_functions()
        self._parse_kwargs()
        self._parse_flags()
        self.run()

    def run(self):
        """
        Run Makefile.py targets specified in the ezmake command

        Run all targets defined in the user's Makefile which were
        passed as an argument to the ezmake command.
        All keyword arguments specified with ``kwarg=value`` are passed
        to those targets which require that kwarg.
        Any additional arguments will be passed to Makefile targets
        which accept ``*args`` and ``**kwargs`` as input arguments.

        """
        for function in self.functions:
            # Get all args and their defaults from the function definition
            argspec = inspect.getargspec(function)
            defaults = list(argspec.defaults) if argspec.defaults else []
            num_args = len(argspec.args)
            num_defaults = len(defaults)
            num_nodefaults = num_args - num_defaults
            # Match the function's args with those passed in the ezmake command
            args = {}
            arg_error = False
            for i, arg in enumerate(argspec.args):
                if self.kwargs.get(arg) is not None:
                    args[arg] = self.kwargs[arg]
                elif self.flags.get(arg):
                    args[arg] = self.flags[arg]
                elif i >= num_nodefaults:
                    args[arg] = defaults[i - num_nodefaults]
                else:
                    arg_error = True
            # If args are missing, rather than rewrite the TypeError logic
            # just call the function, knowing that it will raise a TypeError
            if arg_error:
                function(**args)
            # Handle extra arguments
            extra_args = []
            extra_kwargs = {}
            if argspec.varargs:
                extra_args = [a for a in self.args if a not in argspec.args]
                for f, _ in self.flags.items():
                    extra_args.append(f'-{f}')
            if argspec.keywords:
                extra_kwargs = {k: v for k, v in self.kwargs.items()
                                     if k not in argspec.args}
            # Run function
            function(*args.values(), *extra_args, **extra_kwargs)

    def _parse_args(self):
        """
        Parse all command-line arguments
        """
        parser = argparse.ArgumentParser()
        _, args = parser.parse_known_args()
        self.args = [a for a in args if a != '']

    def _parse_functions(self):
        """
        Find Makefile.py targets specified in the ezmake command

        Finds all targets defined in the user's Makefile which were
        passed as an argument to the ezmake command.

        """
        functions = []
        if not self.args:
            functions.append(next(iter(self.targets.values())))
        else:
            for i in range(len(self.args)):
                if self.targets.get(self.args[0]):
                    functions.append(self.targets[self.args.pop(0)])
                else:
                    if not functions:
                        msg = f'ezmake command args: {self.args} did not ' +  \
                            'match any targets defined in Makefile.py: %s' %\
                            list(self.targets.keys())
                        raise TypeError(msg)
                    break
        self.functions = functions

    def _parse_kwargs(self):
        """
        Separate kwargs from args in the ezmake command-line arguments
        """
        def load_json(s: str):
            try: return json.loads(s)
            except: return s  # noqa

        re_kwargs = r'^[\w_][\w\d_]*=.+$'
        kwargs = [a.split('=') for a in self.args if re.findall(re_kwargs, a)]
        self.kwargs = {k: load_json(v) for k, v in kwargs}
        self.args = [a for a in self.args if not re.findall(re_kwargs, a)]

    def _parse_flags(self):
        self.flags = {f: True for a in self.args if re.findall(r'^-\w+$', a)
                              for f in a[1:]}
        self.args = [a for a in self.args if not self.flags.get(a[1:])]


def target(function):
    """Decorator"""
    global makefile
    makefile.add_target(function)


makefile = Makefile()
