import os
import importlib.util
from .make import makefile


def main():
    """Entrypoint for ``ezmake`` and ``easymake`` commands"""
    # Load targets from Makefile.py module
    makefile_path = os.path.join(os.getcwd(), 'Makefile.py')
    spec = importlib.util.spec_from_file_location("__main__", makefile_path)
    makefile_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(makefile_module)
    # Run easymake
    makefile.make()


if __name__ == "__main__":
    """Entrypoint for ``python -m easymake`` command"""
    main()
