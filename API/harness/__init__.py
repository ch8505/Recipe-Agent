"""The hand-written harness. One file per responsibility.

Every runtime action is printed as "[<file>.py] ..." via log().
"""
import sys


def log(file: str, msg: str) -> None:
    print(f"[{file}] {msg}", file=sys.stdout, flush=True)
