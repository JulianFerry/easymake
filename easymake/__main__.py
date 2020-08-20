import os
import importlib.util


def main():
    makefile_path = os.path.join(os.getcwd(), 'Makefile.py')
    spec = importlib.util.spec_from_file_location("__main__", makefile_path)
    makefile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(makefile)


if __name__ == "__main__":
    main()
