import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / 'data' / 'jobtracker.db'
LOG_PATH = ROOT / 'logs' / 'jobtracker.log'


class Settings:
    DEFAULTS = {'show_discarded': True, 'confirm_close': True}

    def __init__(self, path: Path = ROOT / 'data' / 'settings.json'):
        self.path = path
        self.values = self.DEFAULTS.copy()
        if path.exists():
            values = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(values, dict):
                raise ValueError('El archivo de preferencias no es un objeto JSON')
            for key in self.DEFAULTS:
                if key in values:
                    if not isinstance(values[key], bool):
                        raise ValueError(f'Preferencia incorrecta: {key}')
                    self.values[key] = values[key]

    def get(self, key: str) -> bool:
        return self.values[key]

    def set(self, key: str, value: bool) -> None:
        if key not in self.DEFAULTS or not isinstance(value, bool):
            raise ValueError('Preferencia no válida')
        updated = {**self.values, key: value}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(updated, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        self.values = updated
