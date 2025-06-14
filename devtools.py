import subprocess
import sys


def format() -> None:
    """Run Black on the ibp package."""
    subprocess.check_call(["black", "ibp", *sys.argv[1:]])


def lint() -> None:
    """Run Pylint on the ibp package."""
    subprocess.check_call(["pylint", "ibp", *sys.argv[1:]])


def typecheck() -> None:
    """Run Mypy on the ibp package."""
    subprocess.check_call(["mypy", "ibp", *sys.argv[1:]])

