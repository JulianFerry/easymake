import os
import re
import json
import demjson
from pathlib import Path

import sys
import shlex
import subprocess

import warnings


def _formatwarning(msg, category, filename, lineno, line=None):
    """Replace filename with __name__ to avoid printing the warn() call"""
    msg = warnings.WarningMessage(msg, category, __name__, lineno, None, None)
    return warnings._formatwarnmsg_impl(msg)
warnings.formatwarning = _formatwarning  # noqa


class Globals(dict):
    """
    Globals is a supercharged Python dictionary in which values can
    reference other dictionary values by key, preceded by the ``$``
    symbol and (optionally) surrounded by curly braces: ``'$key'``
    or ``'${key}'``. If no corresponding dictionary key is found,
    Globals will look for an environment variable whose name matches
    that key.

    When calling the ``.get``, ``__getitem__`` or ``__getattr__``
    methods, if that item references another ``Globals`` key (or an
    environment variable), the returned value will be updated with the
    value corresponding to that key. If the key is not found, then no
    replacement occurs.

    Since ``Globals`` inherits from Python's dictionary class, passing
    a ``Globals`` object as a function argument will pass a reference
    to its position in memory. Therefore, any changes made to a
    ``Globals`` object within the context of a function will also
    change that object within the global context. This allows a
    ``Globals`` object to be assigned to the ``Shell`` class before any
    global values have been set in the *Makefile*. Any future changes
    made to the global object will propagate to the ``Shell`` object.

    Items can also be set and fetched using the ``.`` notation, as if
    they were object attributes.

    Examples
    --------

    >>> from easymake.helpers import Globals
    >>> g = Globals({'a': 'Hello', 'b': 'world!'})
    >>> print(g['a'])
    'Hello'
    >>> print(g.b)
    'world!
    >>> g.c = '$a ${b}'  # g.c references g.a and g.b by name
    >>> print(g.c)
    'Hello world!'
    >>> g.d = 'Personal working directory: $PWD'  # environment variable
    >>> print(g.d)
    Personal working directory: /home/easymake
    >>> g.e = '$other'
    >>> print(g.e)
    RuntimeWarning: $other not found in Globals or OS environment variables
    '$other'

    """
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def from_path(path: str = 'Makefile'):
        """
        Generate global values from a directory structure.

        Using the Makefile.py file path as the starting point,
        ``Globals.from_path`` will generate all names and absolute
        paths for directories specified in the directory structure,
        of the format: ``{'directory_name': name, 'directory_path': abspath}

        The path must end with ``'Makefile'`` since all paths will be
        determined relative to the Makefile's absolute path.

        Parameters
        ----------
        path: str
            Directory structure ending with ``'Makefile'``.

        Examples
        --------
        >>> from easymake.helpers import Globals
        >>> g = Globals.from_path('project/src/package/Makefile')
        >>> print(g)
        {
            'project_path': '/home/myproject',
            'project_name': 'myproject'
            'src_path': '/home/myproject/src',
            'src_name': 'src',
            'package_path': '/home/myproject/src/easymake',
            'package_name': 'easymake',
            'Makefile_path': '/home/myproject/src/easymake/Makefile.py',
            'Makefile_name': 'Makefile.py'
        }

        """
        if not path.endswith('Makefile'):
            raise ValueError('globs path should end with "Makefile"')
        dirs = path.split('/')
        # Start with cwd equal to the Makefile path so that we can iteratively
        # go up the path to find the parent directories
        cwd = os.path.join(os.getcwd(), 'Makefile.py')
        globs = Globals({
            'Makefile_path': Path(os.path.abspath(cwd)),
            'Makefile_name': os.path.basename(cwd)
        })
        for d in dirs[-2::-1]:
            cwd = os.path.dirname(cwd)
            globs[f'{d}_path'] = Path(os.path.abspath(cwd))
            globs[f'{d}_name'] = os.path.basename(cwd)
        return globs

    def __getitem__(self, key):
        """Get item, replacing references to $keys with their values."""
        value = super().__getitem__(key)
        if isinstance(value, str): value = self._replace_variables(value)
        return value

    def __getattr__(self, key):
        """Fetch dict value using dict.key notation."""
        return self.__getitem__(key)

    def get(self, key, default=None):
        """Calls dict.get, replacing references to $keys with their values."""
        value = super().get(key, default)
        if isinstance(value, str): value = self._replace_variables(value)
        return value

    def _replace_variables(
        self,
        string: str
    ):
        """
        Replace $key variables with their corresponding value.

        Defaults to environment variables if no key is found.

        Parameters
        ----------
        string: str
            String to replace variables for.

        """
        # Input handling
        if not isinstance(string, str):
            string = _to_string(string)
        # Find all $ or ${} variables in the string
        quotes = '(?:"|\')'
        alphanums_in_square_brackets = \
            r'(?:'                                                  + \
                r'(?:\[' + quotes + r'[\w_]+' + quotes + r'\])'     + \
                r'|'                                                + \
                r'(?:\[\$[\w_]+\])'                                 + \
                r'|'                                                + \
                r'(?:\[\d+\])'                                      + \
            r')*'
        pattern = \
            r'('                                                    + \
                r'\$[\w_]+' + alphanums_in_square_brackets          + \
                r'|'                                                + \
                r'\${[\w_]+' + alphanums_in_square_brackets + '}'   + \
            r')'
        parsed_variables = re.findall(pattern, string)
        var_replacements = {k: k for k in parsed_variables}
        # Find a replacement for each parsed variable
        for var in parsed_variables:
            # Split var into subkeys if var is of the form $variable['subkey']
            # E.g. "$PATHS['mypath'][$arg']" -> ["$PATHS", "mypath", "$arg"]
            regex = r'\[(?:\'|")?(.*?)(?:\'|")?\]'  # ['.*'] or [".*"]
            subkeys = re.findall(regex, var)
            subkeys.insert(0, re.findall(r'^\${?[\w_]+}?', var)[0])  # ${key}
            # Replace any $variable subkeys with the associated value
            warning = 'not found in Globals or OS environment variables'
            for i, key in enumerate(subkeys):
                if key.startswith('$'):
                    key = key.strip('${}')
                    subkey_value = self.get(key, os.environ.get(key))
                    if subkey_value is not None:
                        # Recursively update any referenced variables
                        subkey_value = self._replace_variables(subkey_value)
                        subkeys[i] = subkey_value
                    else:
                        warnings.warn(f'${key} {warning}', RuntimeWarning)
            # If it's a collection (dict or list), iterate over the subkeys
            # to fetch the element by key / index
            try:
                replacement = subkeys[0]
                for k in subkeys[1:]:
                    if isinstance(replacement, list):
                        replacement = replacement[int(k)]
                    else:
                        replacement = replacement[k]
                var_replacements[var] = replacement
            except (IndexError, KeyError):
                pass
        # Now replace all occurences of that $variable in the original string
        for var, replacement in var_replacements.items():
            replacement = _to_string(replacement)
            string = string.replace(var, replacement)
        return string


class Shell:
    """
    Instantiates a Shell class which can execute shell commands.

    - Calling ``run()`` will run a shell command and stream the output
    - Calling ``capture()`` will return the output of a shell command

    Parameters
    ----------
    globals: Globals
        Global variables to use.
    cwd: str
        Default working directory to execute shell commands from

    """
    def __init__(
        self,
        globals: Globals = None,
        cwd: str = None
    ):
        self.globals = globals
        self.cwd = cwd

    def __call__(
        self,
        command: str,
        cwd=None
    ):
        self.run(command, cwd)

    def run(
        self,
        command: str,
        cwd: str = None
    ):
        """
        Execute a shell command as a subprocess and print the output.

        Parameters
        ----------
        command: str
            Shell command to execute as a string.
        cwd: str
            Directory from which to execute the command.
            This will affect any relative paths in the command.

        """
        self._execute(
            command,
            cwd,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT
        )

    def capture(
        self,
        command: str,
        cwd: str = None
    ):
        """
        Execute a shell command as a subprocess and return the output.

        Parameters
        ----------
        command: str
            Shell command to execute as a string.
        cwd: str
            Directory from which to execute the command.
            This will affect any relative paths in the command.

        Returns
        -------
        stdout: str
            Shell command stdout (errors will be raised).

        """
        return self._execute(
            command,
            cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

    def _execute(
        self,
        command: str,
        cwd: str,
        stdout: object,
        stderr: object
    ):
        """
        Execute a shell command as a subprocess and return the output.

        Parameters
        ----------
        command: str
            Shell command to execute as a string.
        cwd: str
            Directory from which to execute the command.
            This will affect any relative paths in the command.
        stdout:
            IO handler for the command's stdout. Options are:
            - subprocess.PIPE to capture and return the whole output
            - sys.stdout to stream the command output to the console
        stderr:
            IO handler for the command's stderr. Options are:
            - subprocess.PIPE to capture and return the whole output
            - subprocess.STDOUT to stream errors to stdout

        Returns
        -------
        output: str
            Shell command output if stdout is ``subprocess.PIPE``.

        """
        # Parse command
        commands = command.split(';')
        output = ''
        for cmd in commands:
            command_list = shlex.split(cmd)
            if not cwd:
                cwd = self.cwd if self.cwd else os.getcwd()
            # Replace $variables with Globals values
            if isinstance(self.globals, Globals):
                command_list = [
                    self.globals._replace_variables(c) for c in command_list]
                cwd = self.globals._replace_variables(cwd)
            command_list = [_to_string(c) for c in command_list]
            # Run command and capture or stream the output
            p = subprocess.run(
                command_list,
                stdout=stdout,
                stderr=stderr,
                cwd=cwd,
                universal_newlines=True
            )
            if p.returncode != 0:
                msg = '\nCommand `%s` failed with exit code %s' % \
                    (command_list, p.returncode)
                stderr_msg = ':\n\n%s' % p.stderr if p.stderr else ''
                print(msg, stderr_msg)
                quit()  # Quit is more readable than raising an error here
            elif p.stdout:
                output += p.stdout[:-1]
        return output


def _to_string(var):
    """
    Convert single-quoted Python dicts and lists to double-quoted JSON
    Don't add quotes for other types such as int, float and str

    Parameters
    ----------
    var: object
        Any object that can be converted to a string representation

    """
    if isinstance(var, str) and len(var) > 2 and \
            (var[0] != var[-1]) and var[0] not in ['"', "'"]:
        try:
            var = demjson.decode(var)
        except (demjson.JSONDecodeError, AttributeError, TypeError):
            pass
    if isinstance(var, (list, dict)):
        var = json.dumps(var)
    else:
        var = str(var)
    return var
