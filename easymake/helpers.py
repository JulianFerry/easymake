import os
import re
import json
import demjson
from pathlib import Path

import sys
import shlex
import subprocess

from typing import Union
from warnings import warn


class Globals(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    def __init__(self):
        globs = {
            'Makefile_path': Path(os.path.abspath(os.getcwd())),
            'Makefile_name': os.path.basename(os.getcwd())
        }
        super().__init__(globs)

    def from_path(path='Makefile'):
        if not path.endswith('Makefile'):
            raise ValueError('globs path should end with "Makefile"')
        globs = Globals()
        cwd = os.path.join(os.getcwd(), 'Makefile.py')
        dirs = path.split('/')
        for d in dirs[-2::-1]:
            cwd = os.path.dirname(cwd)
            globs[f'{d}_path'] = Path(os.path.abspath(cwd))
            globs[f'{d}_name'] = os.path.basename(cwd)
        return globs


class Shell:
    def __init__(self, globals: Union[Globals, dict]=None):
        self.globals = globals
    
    def __call__(self, command, cwd=None):
        self.run(command, cwd)

    def run(self, command, cwd=None):
        self._subprocess(command, cwd, stdout=sys.stdout)

    def capture(self, command, cwd=None):
        return self._subprocess(command, cwd, stdout=subprocess.PIPE)

    def _subprocess(self, command, cwd, stdout):
        """
        Execute a shell command as a subprocess and return the output

        Parameters
        ----------
        command: str
            Shell command to execute as a string
        cwd: str
            Directory from which to execute the command
            This will affect any relative paths in the command
        stdout:
            IO handler for the command's stdout. Options are:
            - subprocess.PIPE to capture and return the whole output
            - sys.stdout to stream the command output to the console

        Returns
        -------
        output: str
            Shell command output if stdout is subprocess.PIPE

        """
        command_list = shlex.split(command)
        if self.globals:
            command_list = [self._replace_variables(c) for c in command_list]
        command_list = [self._to_string(c) for c in command_list]
        cwd = self._replace_variables(cwd) \
            if isinstance(cwd, str) else os.getcwd()
        p = subprocess.run(
            command_list,
            stdout=stdout,
            stderr=subprocess.PIPE,
            cwd=cwd,
            universal_newlines=True
        )
        if p.returncode != 0:
            raise RuntimeError(
                '\n\nCommand `%s` failed with exit code %s:\n\n%s' % \
                (command_list, p.returncode, p.stderr))
        elif p.stdout:
            return p.stdout[:-1]

    def _replace_variables(
        self,
        command_str: str
    ):
        """
        Replace $variables with their value stored in self.globals
        If no variable is found, defaults to environment variables.

        Parameters
        ----------
        command_str: str
            Command to replace $variables for

        """
        # Find all $ or ${} variables in the string 
        quotes = '(?:"|\')'
        alphanums_in_square_brackets = \
            '(?:'                                                   + \
                '(?:\[' + quotes + '[\w_]+' + quotes + '\])'        + \
                '|'                                                 + \
                '(?:\[\$[\w_]+\])'                                  + \
                '|'                                                 + \
                '(?:\[\d+\])'                                       + \
            ')*'
        pattern = \
            '('                                                     + \
                r'\$[\w_]+' + alphanums_in_square_brackets          + \
                '|'                                                 + \
                r'\${[\w_]+' + alphanums_in_square_brackets + '}'   + \
            ')'
        parsed_variables = re.findall(pattern, command_str)
        var_replacements = {k: k for k in parsed_variables}
        # Find a replacement for each parsed variable
        for var in parsed_variables:
            # Split var into subkeys if var is of the form $variable['subkey']
            # E.g. "$PATHS['mypath'][$arg']" -> ["$PATHS", "mypath", "$arg"]
            regex = '\[' + '(?:\'|")*' + '(.*?)' + '(?:\'|")*' + '\]'  # ['.*']
            subkeys = re.findall(regex, var)
            subkeys.insert(0, re.findall('^\${?[\w_]+}?', var)[0])
            # Replace any $variable subkeys with the associated value
            warning = 'not found in shell globals or OS environment variables'
            for i, key in enumerate(subkeys):
                if key.startswith('$'):
                    key = key.strip('${}')
                    subkeys[i] = self.globals.get(key, os.environ.get(key))
                    if subkeys[i] is None:
                        warn(f'${key} {warning}')
            # If it's a collection (dict or list), iteratively get the element
            try:
                replacement = subkeys[0]
                for k in subkeys[1:]:
                    if isinstance(replacement, list):
                        replacement = replacement[int(k)]
                    else:
                        replacement = replacement[k]
                var_replacements[var] = replacement
            except:
                pass
        # Now replace all occurences of that variable in the parsed string
        for var, replacement in var_replacements.items():
            replacement = self._to_string(replacement)
            command_str = command_str.replace(var, replacement)
        return command_str
    
    def _to_string(self, variable):
        """
        Convert single quoted Python dict strings to double quoted JSON
        Don't add quotes for strings and ints

        """
        try: variable = demjson.decode(variable)
        except: pass
        if isinstance(variable, (list, dict)):
            variable = json.dumps(variable)
        else:
            variable = str(variable)
        return variable