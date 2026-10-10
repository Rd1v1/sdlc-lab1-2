"""Validate YAML structure and exercise actual negative test/security gates."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    os.environ['PYTHONUTF8'] = '1'
    config = yaml.safe_load(Path('.github/workflows/main.yml').read_text(encoding='utf-8'))
    assert set(config['jobs']) == {'build', 'test', 'sast', 'deploy'}
    assert config['permissions'] == {'contents': 'read'}
    assert config['jobs']['test']['needs'] == 'build'
    assert config['jobs']['sast']['needs'] == 'test'
    assert config['jobs']['deploy']['needs'] == 'sast'
    Path('artifacts').mkdir(exist_ok=True)
    failure = subprocess.run([sys.executable, 'scripts/test.py', '--lab', '1', '--failure-probe', '--junit', 'artifacts/failure-probe.xml'], capture_output=True, text=True, encoding='utf-8')
    assert failure.returncode == 1, failure.stdout + failure.stderr
    assert int(ET.parse('artifacts/failure-probe.xml').getroot().get('failures')) == 1
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        fixture = Path(directory) / 'insecure.py'
        # Static-only positive fixture. It is never imported or executed.
        fixture.write_text('import subprocess\nsubprocess.call("echo " + input(), shell=True)\n', encoding='utf-8')
        scan = subprocess.run([sys.executable, '-m', 'bandit', str(fixture), '-lll', '-f', 'json'], capture_output=True, text=True, encoding='utf-8')
        assert scan.returncode == 1, scan.stdout + scan.stderr
    print('PASS: YAML/jobs, real test failure exit=1/JUnit, SAST High exit=1')


if __name__ == '__main__':
    main()
