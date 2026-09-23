import pytest
from app.config.settings import Settings


def test_settings_persistence(tmp_path):
    path = tmp_path / 'settings.json'
    settings = Settings(path)
    settings.set('show_discarded', False)
    settings.set('confirm_close', False)
    reopened = Settings(path)
    assert not reopened.get('show_discarded')
    assert not reopened.get('confirm_close')


def test_invalid_settings(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text('{"confirm_close": "false"}', encoding='utf-8')
    with pytest.raises(ValueError):
        Settings(path)
