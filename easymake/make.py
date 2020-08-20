import re
import json
import inspect
import argparse


class Makefile:
    """
    Parses a Makefile.py script via the same logic as a Makefile

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
        All keyword arguments specified with `kwarg=value` are passed
        to those functions which require that kwarg.
        Any additional arguments will be passed to Makefile functions
        which accept ``*args`` and ``**kwargs`` as input arguments.

        """
        for function in self.functions:
            # Function arguments
            argspec = inspect.getargspec(function)
            function_args = argspec.args
            kwargs = {k: v for (k, v) in self.kwargs.items() if k in function_args}
            flags = {f: True for f in self.flags if f in function_args}
            # Extra arguments
            extra_args = self.args if argspec.varargs else []
            extra_kwargs = self.kwargs if argspec.keywords else {}
            # Run
            function(*extra_args, **kwargs, **flags, **extra_kwargs)

    def _parse_args(self):
        """
        Parse all command-line arguments
        """
        parser = argparse.ArgumentParser()
        _, args = parser.parse_known_args()
        self.args = args

    def _parse_functions(self, locals: dict):
        """
        Find all functions defined in the user's Makefile which were
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
                        msg = f'ezmake command args: {self.args} did not match' + \
                            ' any functions defined in Makefile.py: %s' % \
                            list(functions_dict.keys())
                        raise ValueError(msg)
                    break
        self.functions = functions

    def _isfunction(self, dict_item: tuple):
        k, v = dict_item
        return callable(v) and (v.__module__ == "__main__")

    def _parse_kwargs(self):
        """
        Separate kwargs from args in the ezmake command-line arguments
        """
        kwarg_regex = r'^[\w_][\w\d_]*=.+$'
        kwargs = [a.split('=') for a in self.args if re.findall(kwarg_regex, a)]
        kwargs = {k: (v if isinstance(v, str) else json.loads(v)) for k, v in kwargs}
        args = [a for a in self.args if not re.findall(kwarg_regex, a)]
        self.kwargs = kwargs
        self.args = args

    def _parse_flags(self):
        flags = [f for a in self.args if re.findall(r'^-\w+$', a) for f in a[1:]]
        self.flags = flags


def make(locals):
    makefile = Makefile(locals)
    makefile.run()
