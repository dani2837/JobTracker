from copy import deepcopy
from datetime import date, timedelta
from time import monotonic, sleep
import socket

import pytest
from PySide6.QtWidgets import QApplication
from app.config import profile as profiles
from app.config.settings import Settings
from app.services.scoring.engine import ScoringEngine
from app.ui.main_window import MainWindow
from tests.test_ui import application, window


@pytest.fixture
def isolated_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, 'USER_PROFILE_PATH', tmp_path / 'search_profile.json')


def customized():
    profile = profiles.load_profile(profiles.PROFILE_PATH)
    profile['search_preferences'] = deepcopy(profiles.search_preferences(profile))
    return profile


def test_profile_ui_save_restart_restore_and_no_unrequested_recalculation(window, isolated_profile):
    view = window.configuration
    before = window.jobs.repository.get_all_jobs()
    assert view.max_age.value() == 60 and view.max_experience.value() == 1
    view.modalities['onsite'].setChecked(False)
    view.categories['qa'].setChecked(False)
    view.max_experience.setValue(3)
    view.max_age.setValue(14)
    view.exclude_university.setChecked(False)
    view.save_profile_button.click()
    profile = profiles.load_profile()
    assert profile['max_required_experience_years'] == 3
    assert profile['university_degree'] is False  # La preferencia no inventa una titulación.
    assert window.jobs.repository.get_all_jobs() == before
    reopened = MainWindow(window.db, Settings(window.settings.path))
    try:
        saved = reopened.configuration
        assert saved.max_age.value() == 14 and not saved.modalities['onsite'].isChecked()
        assert not saved.categories['qa'].isChecked() and not saved.exclude_university.isChecked()
        saved.restore_profile_button.click()
        assert profiles.load_profile() == profiles.load_profile(profiles.PROFILE_PATH)
        assert saved.max_age.value() == 60 and saved.categories['qa'].isChecked()
    finally:
        reopened.close()


def test_save_and_recalculate_is_sqlite_only(window, isolated_profile, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Red prohibida')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    before = window.jobs.repository.get_all_jobs()
    view = window.configuration
    view.max_experience.setValue(2)
    view.max_age.setValue(1)
    view.save_recalculate_button.click()
    assert window.worker is not None and not view.save_profile_button.isEnabled()
    deadline = monotonic() + 10
    while window.worker is not None and monotonic() < deadline:
        QApplication.processEvents()
        sleep(.01)
    assert window.worker is None
    assert view.save_profile_button.isEnabled() and 'Sin consultar Internet' in view.profile_label.text()
    after = window.jobs.repository.get_all_jobs()
    assert all(j['score_details'] for j in after)
    assert {j['id']: (j['status'], j['is_new']) for j in before} == {j['id']: (j['status'], j['is_new']) for j in after}
    assert ScoringEngine().profile['max_required_experience_years'] == 2


@pytest.mark.parametrize('preference,value,job', [
    ('modalities', ['hybrid', 'remote'], {'modality': 'Presencial'}),
    ('modalities', ['onsite', 'remote'], {'modality': 'Híbrido'}),
    ('modalities', ['onsite', 'hybrid'], {'modality': 'Remoto', 'location': 'España'}),
    ('seville', False, {'modality': 'Presencial'}),
    ('remote_spain', False, {'modality': 'Remoto', 'location': 'España'}),
    ('categories', ['qa'], {'title': 'Desarrollador Python'}),
    ('categories', ['systems'], {'title': 'Data Engineer'}),
    ('max_age_days', 7, {'published_date': (date.today() - timedelta(days=8)).isoformat()}),
])
def test_saved_preferences_are_applied_by_existing_engine(preference, value, job):
    profile = customized()
    profile['search_preferences'][preference] = value
    result = ScoringEngine(profile).evaluate({'title': 'Desarrollador Python', 'location': 'Sevilla', **job})
    assert result.excluded and 'search_preferences' in result.facts['exclusion_categories']


def test_university_experience_age_boundary_and_missing_date():
    profile = customized()
    job = dict(title='Desarrollador Python', location='Sevilla', description='Requisito obligatorio: grado universitario.')
    assert ScoringEngine(profile).evaluate(job).excluded
    profile['search_preferences']['exclude_university'] = False
    assert not ScoringEngine(profile).evaluate(job).excluded
    job['description'] = 'Se requiere experiencia mínima de 2 años.'
    assert ScoringEngine(profile).evaluate(job).excluded
    profile['max_required_experience_years'] = 2
    assert not ScoringEngine(profile).evaluate(job).excluded
    job['published_date'] = (date.today() - timedelta(days=60)).isoformat()
    assert not ScoringEngine(profile).evaluate(job).excluded
    job['published_date'] = None
    assert not ScoringEngine(profile).evaluate(job).excluded


def test_invalid_profile_does_not_replace_saved_file(isolated_profile):
    profile = customized()
    profiles.save_profile(profile)
    previous = profiles.USER_PROFILE_PATH.read_bytes()
    profile['search_preferences']['modalities'] = []
    with pytest.raises(ValueError):
        profiles.save_profile(profile)
    assert profiles.USER_PROFILE_PATH.read_bytes() == previous
