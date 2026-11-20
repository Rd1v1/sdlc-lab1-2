"""Validate YAML structure and exercise actual negative test/security gates."""
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import yaml
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    os.environ['PYTHONUTF8'] = '1'
    config = yaml.safe_load(Path('.github/workflows/main.yml').read_text(encoding='utf-8'))
    assert set(config['jobs']) == {'build', 'test', 'sast', 'sca', 'deploy'}
    assert config['permissions'] == {'contents': 'read'}
    assert config['jobs']['test']['needs'] == 'build'
    assert config['jobs']['sast']['needs'] == 'test'
    assert config['jobs']['sca']['needs'] == 'test'
    assert set(config['jobs']['deploy']['needs']) == {'sast', 'sca'}
    Path('artifacts').mkdir(exist_ok=True)
    failure = subprocess.run([sys.executable, 'scripts/test.py', '--failure-probe', '--junit', 'artifacts/failure-probe.xml'], capture_output=True, text=True, encoding='utf-8')
    assert failure.returncode == 1, failure.stdout + failure.stderr
    assert int(ET.parse('artifacts/failure-probe.xml').getroot().get('failures')) == 1
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        fixture = Path(directory) / 'insecure.py'
        # Static-only positive fixture. It is never imported or executed.
        fixture.write_text('import subprocess\nsubprocess.call("echo " + input(), shell=True)\n', encoding='utf-8')
        sast_report = ROOT / 'artifacts/sast-failure-probe.json'
        scan = subprocess.run([sys.executable, '-m', 'bandit', str(fixture), '-lll', '-f', 'json', '-o', str(sast_report)], capture_output=True, text=True, encoding='utf-8')
        assert scan.returncode == 1, scan.stdout + scan.stderr
        # Query a known vulnerable version without installing or running it.
        requirements = Path(directory) / 'vulnerable-requirements.txt'
        requirements.write_text('pip==24.2\n', encoding='utf-8')
        report = ROOT / 'artifacts/sca-failure-probe.json'
        audit = subprocess.run([
            sys.executable, '-m', 'pip_audit', '-r', str(requirements),
            '--no-deps', '--disable-pip', '--strict',
            '--cache-dir', str(ROOT / '.cache/pip-audit'),
            '--progress-spinner', 'off', '--format', 'json', '--output', str(report),
        ], capture_output=True, text=True, encoding='utf-8', timeout=120)
        assert audit.returncode == 1, audit.stdout + audit.stderr
        dependencies = json.loads(report.read_text(encoding='utf-8'))['dependencies']
        assert any(item['name'] == 'pip' and item['vulns'] for item in dependencies)
        for tool, source in [('bandit', sast_report), ('pip-audit', report)]:
            exported = subprocess.run([sys.executable, 'scripts/security_reports.py', tool, str(source)], capture_output=True, text=True, encoding='utf-8')
            assert exported.returncode == 0, exported.stdout + exported.stderr
            assert ET.parse(source.with_suffix('.xml')).getroot().get('tool') == tool
            assert len(PdfReader(source.with_suffix('.pdf')).pages) >= 1
    print('PASS: YAML/jobs, real test failure exit=1/JUnit, SAST High exit=1, SCA vulnerable package exit=1; negative scan reports exported to XML/PDF')


if __name__ == '__main__':
    main()
