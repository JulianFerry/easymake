import re
import json
import inspect
import argparse


class Makefile:
    """
    Parse a Makefile.py script with the same logic as a Makefile

    ##### UDPATE THIS DOCSTRING ######
    The main way to interact with this class is via the run() method
    Command-line arguments are parsed with argparse:
        - function names: this should be specified in the user's makefile
        - keyword arguments: these will be passed to the Makefile functions
    ##### UDPATE THIS DOCSTRING ######

    Parameters
    ----------
    locals: dict
        Dictionary of Makefile functions returned by locals()

    """
    def __init__(self, locals: dict):
        self._parse_args()
        self._parse_functions(locals)
        self._parse_kwargs()
        self._parse_flags()

    def run(self):
        """
        Run Makefile.py functions specified in the ezmake command

        Run all functions defined in the user's Makefile which were
        passed as an argument to the ezmake command.
        All keyword arguments specified with ``kwarg=value`` are passed
        to those functions which require that kwarg.
        Any additional arguments will be passed to Makefile functions
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

    def _parse_functions(self, locals: dict):
        """
        Find Makefile.py functions specified in the ezmake command

        Finds all functions defined in the user's Makefile which were
        passed as an argument to the ezmake command.

        Parameters
        ----------
        locals: dict
            Dictionary of Makefile variables, as returned by locals()

        """
        functions_dict = dict(filter(self._isfunction, locals.items()))
        functions = []
        if not self.args:
            functions.append(next(iter(functions_dict.values())))
        else:
            for i in range(len(self.args)):
                if functions_dict.get(self.args[0]):
                    functions.append(functions_dict[self.args.pop(0)])
                else:
                    if not functions:
                        msg = f'ezmake command args: {self.args} did not ' +  \
                            'match any functions defined in Makefile.py: %s' %\
                            list(functions_dict.keys())
                        raise TypeError(msg)
                    break
        self.functions = functions

    def _isfunction(self, dict_item: tuple):
        k, v = dict_item
        return callable(v) and (v.__module__ == "__main__")

    def _parse_kwargs(self):
        """
        Separate kwargs from args in the ezmake command-line arguments
        """
        re_kwargs = r'^[\w_][\w\d_]*=.+$'
        kwargs = [a.split('=') for a in self.args if re.findall(re_kwargs, a)]
        self.kwargs = {k: self._load_json(v) for k, v in kwargs}
        self.args = [a for a in self.args if not re.findall(re_kwargs, a)]

    def _parse_flags(self):
        self.flags = {f: True for a in self.args if re.findall(r'^-\w+$', a)
                              for f in a[1:]}
        self.args = [a for a in self.args if not self.flags.get(a[1:])]

    def _load_json(self, s: str):
        try:
            return json.loads(s)
        except Exception:
            return s


def make(locals):
    makefile = Makefile(locals)
    makefile.run()
