import pytest
import json
from pathlib import Path
from app.database.db import Database


@pytest.fixture(autouse=True)
def isolated_test_profile(tmp_path, monkeypatch):
    """Synthetic boundary conditions; never read or overwrite a user's profile."""
    from app.config import profile as profiles
    from app.ui import settings_view
    profile = json.loads(profiles.EXAMPLE_PROFILE_PATH.read_text(encoding='utf-8'))
    profile.update(name='Synthetic regression profile', education=['Formación técnica de ejemplo'],
                   university_degree=False, professional_experience_years=0,
                   max_required_experience_years=1,
                   languages={'espanol': 'nativo', 'ingles': 'intermedio'})
    profile.pop('search_preferences', None)
    path = tmp_path / 'fixture-profile.json'
    path.write_text(json.dumps(profile, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(profiles, 'PROFILE_PATH', path)
    monkeypatch.setattr(profiles, 'USER_PROFILE_PATH', tmp_path / 'user-profile.json')
    monkeypatch.setattr(settings_view, 'PROFILE_PATH', path)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / 'test.db')
    database.initialize()
    return database
