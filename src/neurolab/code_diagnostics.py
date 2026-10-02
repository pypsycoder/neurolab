"""Ready-made static analysis, retaining rule/location only, never code or messages."""
import json
from pathlib import Path
import subprocess
import sys

RULES = {'F821', 'F822', 'F823'}


def project_diagnostics(items):
    if not isinstance(items, list) or len(items) > 60:
        raise ValueError('diagnostic count invalid')
    projected = []
    for item in items:
        location = item.get('location', {})
        row, column = location.get('row'), location.get('column')
        if item.get('code') not in RULES or type(row) is not int or type(column) is not int or not 1 <= row <= 500 or not 1 <= column <= 16000:
            raise ValueError('diagnostic boundary invalid')
        projected.append({'code': item['code'], 'line': row, 'column': column})
    return projected


def static_diagnostics(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 16000:
        raise ValueError('diagnostic source boundary invalid')
    result = subprocess.run([sys.executable, '-m', 'ruff', 'check', '--isolated', '--no-cache',
        '--select', ','.join(sorted(RULES)), '--output-format', 'json', str(path)],
        capture_output=True, timeout=15, check=False)
    if result.returncode not in {0, 1} or len(result.stdout) > 200000:
        raise ValueError('static diagnostic failed')
    return project_diagnostics(json.loads(result.stdout))
