import os
import re
import json
import demjson

import sys
import shlex
import subprocess

from typing import Union
import warnings


def formatwarning(msg, category, filename, lineno, line=None):
    """Replace filename with __name__ to avoid printing the warn() call"""
    msg = warnings.WarningMessage(msg, category, __name__, lineno, None, None)
    return warnings._formatwarnmsg_impl(msg)
warnings.formatwarning = formatwarning


class Globals(dict):
    """
    Globals is a supercharged Python dictionary which can reference values
    """
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def from_path(path='Makefile'):
        if not path.endswith('Makefile'):
            raise ValueError('globs path should end with "Makefile"')
        dirs = path.split('/')
        # Start with cwd equal to the Makefile path so that we can iteratively
        # go up the path to find the parent directories
        cwd = os.path.join(os.getcwd(), 'Makefile.py')
        globs = Globals({
            'Makefile_path': os.path.abspath(cwd),
            'Makefile_name': os.path.basename(cwd)
        })
        for d in dirs[-2::-1]:
            cwd = os.path.dirname(cwd)
            globs[f'{d}_path'] = os.path.abspath(cwd)
            globs[f'{d}_name'] = os.path.basename(cwd)
        return globs

    def __getitem__(self, key):
        """Replace $values when the key is fetched"""
        value = super().__getitem__(key)
        if isinstance(value, str): value = self._replace_variables(value)
        return value

    def __getattr__(self, key):
        """Fetch dict value using dict.key notation"""
        return self.__getitem__(key)

    def get(self, key, default=None):
        """Replace $values when the key is fetched"""
        value = super().get(key, default)
        if isinstance(value, str): value = self._replace_variables(value)
        return value

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
                    subkey_value = self.get(key, os.environ.get(key))
                    if subkey_value is not None:
                        subkeys[i] = subkey_value
                    else:
                        warnings.warn(f'${key} {warning}', RuntimeWarning)
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
            replacement = _to_string(replacement)
            command_str = command_str.replace(var, replacement)
        return command_str


class Shell:
    def __init__(self, globals: Union[Globals, dict]=None):
        self.globals = globals
    
    def __call__(self, command, cwd=None):
        self.run(command, cwd)

    def run(self, command, cwd=None):
        self._execute(command, cwd, stdout=sys.stdout, stderr=subprocess.STDOUT)

    def capture(self, command, cwd=None):
        return self._execute(command, cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _execute(self, command, cwd, stdout, stderr):
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
        if not cwd: cwd = os.getcwd()
        if isinstance(self.globals, Globals):
            command_list = [self.globals._replace_variables(c) for c in command_list]
            cwd = self.globals._replace_variables(cwd)
        command_list = [_to_string(c) for c in command_list]
        p = subprocess.run(
            command_list,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
            universal_newlines=True
        )
        if p.returncode != 0:
            print()
            msg = '\nCommand `%s` failed with exit code %s' % \
                (command_list, p.returncode)
            stderr_msg = ':\n\n%s' % p.stderr if p.stderr else ''
            raise RuntimeError(msg + stderr_msg)
        elif p.stdout:
            return p.stdout[:-1]

def _to_string(variable):
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
