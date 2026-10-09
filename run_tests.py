"""Isolated regression suite: never uses real credentials or external network."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='nebo-tests-') as data:
        os.environ['APPDATA'] = data
        os.environ['NEBO_DATA_DIR'] = data
        with patch('requests.sessions.Session.request', side_effect=AssertionError('External HTTP forbidden in tests')):
            suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / 'tests'))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
