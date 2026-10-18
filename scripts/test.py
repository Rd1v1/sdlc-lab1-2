"""Shared local/CI unittest runner with a dependency-free JUnit report."""
import argparse
import compileall
import os
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from scripts.junit import JUnitResult


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--lab', choices=['1'], default='1')
    parser.add_argument('--junit', type=Path, default=Path('artifacts/junit.xml'))
    parser.add_argument('--failure-probe', action='store_true', help='Deliberate failure to verify CI exit code')
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    tempfile.tempdir = str(scratch)
    for key in ('TMP', 'TEMP', 'TMPDIR'):
        os.environ[key] = str(scratch)
    for source in ('lab1/src', 'scripts'):
        if not compileall.compile_dir(ROOT / source, quiet=1):
            return 1
    suite = unittest.TestLoader().discover(str(ROOT / 'lab1/tests'))
    if args.failure_probe:
        class DeliberateFailure(unittest.TestCase):
            def runTest(self):
                self.fail('Intentional CI failure probe')
        suite.addTest(DeliberateFailure())
    result = unittest.TextTestRunner(verbosity=2, resultclass=JUnitResult).run(suite)
    report = ET.Element('testsuite', tests=str(result.testsRun), failures=str(len(result.failures)),
                        errors=str(len(result.errors)), skipped=str(len(result.skipped)))
    report.extend(result.cases)
    args.junit.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(report).write(args.junit, encoding='utf-8', xml_declaration=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
