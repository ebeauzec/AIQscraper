"""
run_tests.py - ARIA/AIQscraper regression suite entry point
=============================================================
Stdlib-only. Run before committing changes to tools/asup_parser.py or
server.py's multi-account logic:

    python tests/run_tests.py

Discovers and runs every test_*.py module in this directory.
"""

import sys
import unittest
from pathlib import Path

if __name__ == "__main__":
    here = Path(__file__).parent
    loader = unittest.TestLoader()
    suite = loader.discover(str(here), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
