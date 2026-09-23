"""Inspect staged content, not just ignore rules or working-tree versions."""
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'.gitignore', 'README.md', 'requirements.txt', 'pytest.ini'}
PUBLIC_DIRS = {'app', 'tests', 'docs', 'tools', '.github'}
TEXT_SUFFIXES = {'.py', '.md', '.txt', '.json', '.html', '.sql', '.ini', '.yml', '.yaml'}
PATTERNS = {
    'personal filesystem path': re.compile(r'(?:[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+|/(?:Users|home)/[^/\s]+)'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'access credential': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b'),
    'assigned credential': re.compile(r'''(?i)(?:client_secret|api_key|access_token|password)\s*[=:]\s*["'][^"'\s]{8,}["']'''),
}
EMAIL = re.compile(r'[\w.+-]+@([\w.-]+\.[A-Za-z]{2,})')


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], stderr=subprocess.PIPE)


def allowed_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:
        return False
    if name in ROOT_FILES:
        return True
    if not path.parts or path.parts[0] not in PUBLIC_DIRS:
        return False
    if any(p in {'__pycache__', '.pytest_cache', '.venv', 'venv', 'data', 'logs', '.git'} for p in path.parts):
        return False
    if (name == 'app/config/profile.json' or path.name.startswith(('.env', 'credentials', 'secrets'))
            or path.name.startswith(('manual', 'native_smoke', 'scoring_audit'))
            or path.name == 'compatible_audit.json'):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES


def content_issues(data):
    try:
        value = data.decode('utf-8-sig')
    except UnicodeError:
        return ['unexpected binary or non-UTF-8 file']
    findings = [label for label, pattern in PATTERNS.items() if pattern.search(value)]
    if any(domain.casefold() not in {'example.com', 'example.org', 'example.net'}
           for domain in EMAIL.findall(value)):
        findings.append('email address')
    return findings


def staged_files():
    files, problems = {}, []
    for entry in git('ls-files', '--stage', '-z').split(b'\0'):
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        mode, _, stage = metadata.decode().split()
        name = raw_name.decode('utf-8')
        if mode not in {'100644', '100755'} or stage != '0':
            problems.append(f'{name}: unsupported file mode or merge conflict')
            continue
        if not allowed_path(name):
            problems.append(f'{name}: private or unexpected path')
            continue
        data = git('show', ':' + name)
        problems.extend(f'{name}: {issue}' for issue in content_issues(data))
        files[name] = data
    if not files:
        problems.append('No staged public files; run git add first.')
    return files, problems


def main():
    try:
        files, problems = staged_files()
    except subprocess.CalledProcessError:
        print('Cannot read the Git index. Run this tool inside the prepared repository.')
        return 1
    if problems:
        print('\n'.join(problems))
        print('Publication blocked. No sensitive values were printed.')
        return 1
    print(f'OK: {len(files)} staged files; no blocked paths or detected sensitive patterns.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
