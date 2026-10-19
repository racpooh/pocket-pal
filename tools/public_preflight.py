#!/usr/bin/env python3
"""Redacted working-tree hygiene scan. Never invokes Git; not a history/PII audit."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'.git', '.sync', '.pnpm-store', '.venv', 'node_modules', '.next',
                 '.gradle', '.kotlin', '.pytest_cache', '__pycache__', 'build',
                 'bin', 'private', '.idea', '.vscode', 'coverage', '.vercel'}
EXCLUDED_PREFIXES = ('backend/fixtures/real/', 'backend/var/')
PATTERNS = {
    'provider_token': re.compile(r'(?:sk-ant-|sk-proj-|ghp_|github_pat_)[A-Za-z0-9_-]{20,}'),
    'aws_access_id': re.compile(r'AKIA[0-9A-Z]{16}'),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'literal_bearer': re.compile(r'Bearer\s+[A-Za-z0-9_.-]{32,}'),
}
TEXT_SUFFIXES = {'.py', '.kt', '.kts', '.ts', '.tsx', '.js', '.cjs', '.mjs', '.json',
                 '.jsonl', '.xml', '.md', '.txt', '.log', '.sql', '.yml', '.yaml',
                 '.toml', '.lock', '.properties', '.sh', '.bat', '.css', '.svg'}
PRIVATE_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.jks', '.keystore', '.db',
                    '.sqlite', '.sqlite3', '.apk', '.aab', '.mp4', '.mov'}


def scan():
    findings, scanned, excluded = [], 0, 0
    def visit(directory):
        nonlocal scanned, excluded
        for path in sorted(directory.iterdir()):
            rel = path.relative_to(ROOT).as_posix()
            if path.is_symlink():
                findings.append({'path': rel, 'category': 'symlink_requires_review'})
                continue
            if path.name in EXCLUDED_DIRS or any(rel.startswith(p.rstrip('/')) and
                (rel == p.rstrip('/') or rel.startswith(p)) for p in EXCLUDED_PREFIXES):
                excluded += 1
                continue
            if path.is_dir():
                visit(path)
                continue
            if path.name.startswith('.env') and path.name != '.env.example':
                excluded += 1
                continue
            if path.suffix.lower() in PRIVATE_SUFFIXES:
                findings.append({'path': rel, 'category': 'private_or_generated_artifact'})
                continue
            if path.suffix not in TEXT_SUFFIXES and path.name not in {'.gitignore', '.env.example', 'gradlew'}:
                continue
            try:
                content = path.read_text(encoding='utf-8')
            except (UnicodeError, OSError):
                findings.append({'path': rel, 'category': 'text_unreadable'})
                continue
            scanned += 1
            for category, pattern in PATTERNS.items():
                for match in pattern.finditer(content):
                    findings.append({'path': rel, 'line': content.count('\n', 0, match.start()) + 1,
                                     'category': category})
    visit(ROOT)
    return {'scope': 'selected working-tree text only; no Git, history, staging, binary or PII certification',
            'text_files_scanned': scanned, 'excluded_entries': excluded, 'findings': findings}


if __name__ == '__main__':
    result = scan()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['findings']))
