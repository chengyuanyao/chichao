#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run all tests/*_test.py except live integration."""

from __future__ import print_function

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP = {"integration_test.py"}


def main():
    tests_dir = os.path.join(ROOT, "tests")
    names = sorted(
        name for name in os.listdir(tests_dir)
        if name.endswith("_test.py") and name not in SKIP
    )
    failed = []
    for name in names:
        print("\n----- %s -----" % name)
        result = subprocess.call([sys.executable, os.path.join(tests_dir, name)])
        if result != 0:
            failed.append(name)
    if failed:
        print("\nFAILED: %s" % ", ".join(failed))
        return 1
    print("\nAll %d offline tests passed." % len(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
