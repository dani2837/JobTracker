from pathlib import Path
import json

import pytest

from tools.check_publication import allowed_path, content_issues


@pytest.mark.parametrize('name', [
    'data/search_profile.json', 'logs/jobtracker.log', 'app/config/profile.json',
    'FASE7.md', 'tests/manual_live.py', 'tests/fixtures/phase5/compatible_audit.json',
    'app/.env', 'docs/credentials.json', 'app/backup.db', '../outside.py',
])
def test_private_files_cannot_be_exported_even_if_force_added(name):
    assert not allowed_path(name)


def test_public_code_and_fictitious_example_are_allowed():
    assert allowed_path('app/config/profile.example.json')
    assert allowed_path('app/main.py')
    assert allowed_path('.github/workflows/tests.yml')
    assert not content_issues(b'Contact: demo@example.com')


def test_detector_reports_categories_without_disclosing_values():
    value = ('gh' + 'p_' + 'a' * 30).encode()
    findings = content_issues(value)
    assert findings == ['access credential']
    assert value.decode() not in str(findings)


def test_example_is_valid_without_a_private_profile():
    from app.config.profile import EXAMPLE_PROFILE_PATH, validate_profile
    profile = json.loads(EXAMPLE_PROFILE_PATH.read_text(encoding='utf-8'))
    validate_profile(profile)
    assert 'ficticio' in profile['name']
