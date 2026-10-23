"""Reproducible CLI demo; disposable data stays inside the repository."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab1.src import app


def main():
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lab1-demo-', dir=scratch) as directory:
        base = Path(directory)
        with patch.object(app, 'DATA_ROOT', base / 'files'), patch.object(app, 'AUDIT_DATABASE', base / 'audit.db'), patch.object(app.getpass, 'getpass', return_value='local demo password'):
            commands = [
                ['help'], ['pwd'], ['drives'], ['register', 'demo'],
                ['write', 'заметки/мой файл.txt', '--text', 'Привет'],
                ['read', 'заметки/мой файл.txt'],
                ['write', 'заметки/мой файл.txt', '--text', 'Обновлено'],
                ['json-write', 'data.json', '--value', '{"name":"пример","count":3}'],
                ['json-read', 'data.json'],
                ['xml-write', 'data.xml', '--value', '<root><name>Пример</name></root>'],
                ['xml-read', 'data.xml'],
                ['zip-create', 'demo.zip', 'data.json', 'data.xml'],
                ['zip-extract', 'demo.zip', 'unpacked'], ['list'],
                ['delete', 'заметки/мой файл.txt'], ['read', '../outside'], ['exit'],
            ]
            for command in commands:
                if command[0] not in ('help', 'pwd', 'drives', 'register', 'exit'):
                    command += ['--user', 'demo']
                print('>', ' '.join(command), flush=True)
                result = app.run(command)
                expected = 2 if '../outside' in command else 0
                if result != expected:
                    raise RuntimeError(f'Demo failed: {command}, exit={result}')
    print('DEMO PASS (temporary files removed)')


if __name__ == '__main__':
    main()
