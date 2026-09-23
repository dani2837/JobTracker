import json
from pathlib import Path
import pytest
from app.services.scoring.engine import ScoringEngine
from app.services.scoring.location import EXCLUSION
from tests.test_scoring_engine import job


@pytest.mark.parametrize('place,mode,text,accepted', [
    ('Sevilla', None, '', True), ('Sevilla', 'Híbrido', '', True),
    ('Dos Hermanas', None, '', True), ('Alcalá de Guadaíra', None, '', True),
    ('Écija', None, '', True), ('Cartuja', None, '', True),
    ('Madrid', None, '', False), ('Madrid', 'Presencial', '', False),
    ('Madrid', 'Híbrido', '', False), ('Madrid', None, '2 días teletrabajo', False),
    ('España', None, '', False), (None, None, '', False), ('', None, '', False),
    ('Remoto España', None, '', True), ('100% remoto España', None, '', True),
    ('Remote Spain', None, '', True), ('Spain remote', None, '', True),
    ('Madrid', None, '100% remoto desde cualquier lugar de España', True),
    ('Madrid', 'Remoto', '', False), ('Madrid, Spain', 'Teletrabajo disponible', '', False),
    ('Madrid', None, 'Teletrabajo completo desde cualquier punto de España', True),
    ('Madrid', None, 'Remoto España. Modelo híbrido en Madrid.', False),
    ('Madrid', None, 'No se permite remoto España.', False),
    ('Madrid', None, 'No es 100% remoto España.', False),
    ('Madrid', None, '2 días en remoto España.', False),
    ('Madrid', None, 'Teletrabajo parcial. Remoto España.', False),
    ('Madrid', None, 'Remoto España. Formación presencial opcional.', True),
    ('Madrid', None, '100 % remoto España. Experiencia en Apigee Hybrid.', True),
    ('Madrid', None, 'Somos una empresa en España. Trabajo en remoto.', False),
    ('Aguadulce, Almería', None, '', False),
])
def test_strict_location(place, mode, text, accepted):
    result = ScoringEngine().evaluate(job(text, location=place, modality=mode, remote=1,
                                         source_url='https://careers.soprasteria.es/jobs'))
    assert result.excluded is not accepted
    if not accepted:
        assert EXCLUSION in result.facts['exclusion_reasons']
        assert result.score == 0


@pytest.mark.parametrize('text,excluded', [
    ('Ingeniería obligatoria', True), ('Grado universitario obligatorio', True),
    ('Grado valorable', False), ('Grado o equivalente', False), ('Grado o FP', False),
    ('Ingeniería o formación equivalente', False),
    ('Requisitos\nMáster o Ingeniería Superior en Informática (imprescindible)', True),
    ('Requisitos\nTítulo oficial de máster en un ámbito técnico', True),
    ('Requisitos\nScrum master con experiencia en ingeniería de procesos', False),
    ('Requisitos\nPara ello, nos gustaría que aportaras...\nTitulación de grado y máster o ingeniería superior TIC.', False),
    ('Grado universitario obligatorio, FP valorable', True),
    ('Ingeniería obligatoria o experiencia equivalente', False),
    ('Grado obligatorio o Ciclo Formativo', False),
])
def test_degree_audit(text, excluded):
    result = ScoringEngine().evaluate(job(text))
    assert result.excluded is excluded
    if excluded:
        assert 'Titulación universitaria obligatoria no compatible con el perfil.' in result.facts['exclusion_reasons']


@pytest.mark.parametrize('text,language,unmet', [
    ('Francés B2 obligatorio', 'frances', True), ('Francés valorable', 'frances', False),
    ('Alemán C1 obligatorio', 'aleman', True), ('Inglés B1 obligatorio', 'ingles', False),
    ('Inglés B2 obligatorio', 'ingles', False), ('Inglés C1 obligatorio', 'ingles', True),
    ('Inglés C2 obligatorio', 'ingles', True), ('Inglés C1 valorable', 'ingles', False),
    ('Inglés B2 valorable', 'ingles', False), ('Italiano obligatorio', 'italiano', True),
    ('Portugués fluido obligatorio', 'portugues', True), ('Requisitos\nCatalán', 'catalan', True),
    ('Requisitos\nNivel muy alto de francés.', 'frances', True),
    ('Buscamos un perfil técnico con inglés C1.', 'ingles', True),
    ('Requisitos\nInglés B1 y francés C1', 'ingles', False),
    ('Requisitos\nInglés B1 y francés C1', 'frances', True),
    ('Requisitos\nEspañol nativo y alemán B2', 'espanol', False),
    ('Requisitos\nEspañol nativo y alemán B2', 'aleman', True),
])
def test_language_audit(text, language, unmet):
    result = ScoringEngine().evaluate(job(text))
    assert ('language_' + language in result.facts['unmet_categories']) is unmet
    assert any(item['language'] == language for item in result.facts['languages_detected'])
    if text == 'Inglés B2 obligatorio':
        assert result.penalties['english_b2'] > 0 and result.warnings


def test_academic_preference_does_not_hide_language():
    result = ScoringEngine().evaluate(job('Requisitos\nNos gustaría que tuvieras estas titulaciones:\n'
        '• Ingeniería Informática.\n• B2 Francés\nInformación adicional'))
    assert 'education' not in result.facts['exclusion_categories']
    assert result.facts['unmet_categories'] == ['language_frances']
    assert not result.excluded and result.penalties['one_unmet'] == 15


def test_all_red_lines_survive_and_junior_cannot_compensate():
    result = ScoringEngine().evaluate(job('Requisitos\nMínimo 5 años. Ingeniería obligatoria. Francés B2 obligatorio.',
                                         title='Junior Developer', location='Madrid', modality=None))
    assert {'experience', 'education', 'location', 'languages'} <= set(result.facts['exclusion_categories'])
    assert len(result.facts['exclusion_reasons']) >= 3
    assert result.excluded and result.score == 0 and result.classification == 'Excluida'


def test_one_language_penalizes_two_exclude():
    engine = ScoringEngine()
    one = engine.evaluate(job('Francés B2 obligatorio'))
    two = engine.evaluate(job('Francés B2 obligatorio. Alemán C1 obligatorio.'))
    assert not one.excluded and one.penalties['one_unmet'] == 15
    assert two.excluded and 'languages' in two.facts['exclusion_categories']


CASES = json.loads((Path(__file__).parent / 'fixtures/scoring_regressions.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda c: str(c['id']))
def test_offer_requirement_regressions(case):
    result = ScoringEngine().evaluate(case['job'])
    assert set(result.facts['exclusion_categories']) == set(case['expected_categories'])
    assert set(result.facts['unmet_categories']) == set(case['expected_unmet'])
    assert result.excluded and result.score == 0


def test_audit_is_local_complete_and_preserves_database(db, tmp_path, monkeypatch):
    import sys
    from app.services.scoring.audit import main, diagnose
    from app.database.repositories import JobRepository
    from app.services.seed_data import seed_database
    seed_database(db)
    repo = JobRepository(db)
    repo.add(external_id='audit', title='Junior Developer', company_id=1,
             location='Madrid', modality=None, description='Requisitos\nFrancés B2 obligatorio.',
             score=81)
    with db.connect() as connection:
        connection.execute("UPDATE jobs SET source_name='Sopra Steria', is_test_data=0 WHERE external_id='audit'")
    original = repo.get_all_jobs()
    monkeypatch.setattr('httpx.Client.request', lambda *a, **k: pytest.fail('El diagnóstico intentó usar la red'))
    output = tmp_path / 'audit.md'
    monkeypatch.setattr(sys, 'argv', ['audit', '--database', str(db.path), '--output', str(output)])
    main()
    assert repo.get_all_jobs() == original
    text = output.read_text(encoding='utf-8')
    for field in ('Ubicación original', 'Modalidad original', 'Remoto completo', 'Experiencia original',
                  'Formación detectada', 'Idiomas obligatorios', 'Señales junior', 'Requisitos obligatorios',
                  'Requisitos valorables', 'Requisitos incumplidos', 'Score:', 'clasificación:', 'excluded:', EXCLUSION):
        assert field in text
    monkeypatch.setattr(sys, 'argv', ['audit', '--database', str(db.path), '--output', str(output), '--recalculate'])
    main()
    records = diagnose(repo.get_all_jobs())
    assert len(records) == 1 and records[0]['result']['excluded']
