import re
import json
import inspect
import argparse


class Makefile:
    """
    Parses a Makefile.py script via the same logic as a Makefile
    
    ##################################
    ##### UDPATE THIS DOCSTRING ######
    The main way to interact with this class is via the run() method
    Command-line arguments are parsed with argparse:
        function names: this should be specified in the user's makefile
        keyword arguments: these will be passed to the Makefile functions
    ##### UDPATE THIS DOCSTRING ######
    ##################################

    Parameters
    ----------
    locals: dict
        Dictionary of local module variables, as returned by locals()

    """
    def __init__(self, locals: dict):
        """
        """
        self.args = self._parse_args()
        self.kwargs = self._parse_kwargs()
        self.flags = self._parse_flags()
        self.functions = self._parse_functions(locals)
        
    def run(self):
        """
        Run all functions specified in the easymake command,
        which have been defined in the user's Makefile.
        All keyword arguments specified with `kwarg=value` are passed
        to functions which require that kwarg.
        """
        for function in self.functions:
            function_args = inspect.getargspec(function).args
            kwargs = {k: v for (k, v) in self.kwargs.items() if k in function_args}
            flags = {f: True for f in self.flags if f in function_args}
            function(**kwargs, **flags)

    def _parse_args(self):
        """
        Parse all command-line arguments 
        """
        parser = argparse.ArgumentParser()
        _, args = parser.parse_known_args()
        return args

    def _parse_kwargs(self):
        kwargs = [a.split('=') for a in self.args if re.findall(r'^[\w_]+=.+$', a)]
        kwargs = {item[0]: json.loads(item[1]) for item in kwargs}
        return kwargs

    def _parse_flags(self):
        flags = [f for a in self.args if re.findall(r'^-\w+$', a) for f in a[1:]]
        return flags

    def _parse_functions(self, locals: dict):
        """
        """
        functions_dict = dict(filter(self._isfunction, locals.items()))
        functions = []
        for i in range(len(self.args)):
            if functions_dict.get(self.args[0]):
                functions.append(functions_dict[self.args.pop(0)])
            else:
                break
        if not functions:
            functions = [next(iter(functions_dict.values()))]
        return functions

    def _isfunction(self, dict_item: tuple):
        k, v = dict_item
        return callable(v) and (v.__module__ == "__main__")


def make(locals):
    makefile = Makefile(locals)
    makefile.run()
