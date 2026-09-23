from copy import deepcopy
import pytest
from app.config.profile import load_profile
from app.services.scoring.engine import ScoringEngine, classify


def job(description='', **kwargs):
    return {'title': 'Developer', 'description': description, 'location': 'Sevilla', 'modality': 'Presencial', **kwargs}


@pytest.fixture
def engine():
    return ScoringEngine()


@pytest.mark.parametrize('text,excluded', [
    ('0-2 años', False), ('entre 0 y 2 años', False), ('0 to 2 years', False),
    ('hasta 2 años', False), ('0–1 años', False), ('junior', False),
    ('sin experiencia', False), ('no se requiere experiencia', False),
    ('entry level', False), ('trainee', False), ('primer empleo', False),
    ('mínimo 2 años', True), ('al menos 3 años', True), ('3 años', True),
    ('4+ años', True), ('2 años de experiencia requeridos', True),
    ('2 años valorables', False), ('Se valorará tener 5 años de experiencia', False),
    ('Imprescindible Java y 2 años de experiencia', True),
    ('Al menos dos años de experiencia', True), ('mínimo\ndos años de experiencia', True),
    ('Requisitos\n3 años de experiencia.\nInformación adicional\nFormación continua', True),
    ('Somos una empresa con 30 años de historia.', False),
    ('Requisitos deseables\n3 años de experiencia.', False),
    ('Docker valorable y mínimo 2 años de experiencia', True),
    ('2 años valorables y Java obligatorio', False),
    ('Imprescindible entre 0 y 2 años y Docker valorable', False),
])
def test_experience_red_lines(engine, text, excluded):
    result = engine.evaluate(job(text))
    assert result.excluded is excluded, result.to_dict()


def test_experience_scores_and_senior_scope(engine):
    assert engine.evaluate(job('Sin experiencia')).score_breakdown['experience'] == 35
    assert engine.evaluate(job('0-1 años')).score_breakdown['experience'] == 33
    assert engine.evaluate(job('0-2 años')).score_breakdown['experience'] == 30
    assert engine.evaluate(job(title='Junior Developer')).score_breakdown['experience'] == 27
    assert engine.evaluate(job('Trabajarás junto a un equipo senior.', title='Junior Developer')).excluded is False
    assert engine.evaluate(job(title='Senior Developer')).excluded
    assert engine.evaluate(job(experience_level='Senior')).excluded


@pytest.mark.parametrize('text,excluded', [
    ('FP Superior', False), ('DAW', False), ('Grado o equivalente', False),
    ('Grado universitario valorable', False), ('Grado universitario obligatorio', True),
    ('Grado universitario o FP', False), ('Ingeniería obligatoria', True),
    ('Licenciatura obligatoria', True), ('Preferiblemente grado', False),
    ('Se valorará ingeniería', False), ('Grado universitario obligatorio o formación equivalente', False),
    ('CFGS obligatorio', False), ('Grado Superior obligatorio', False),
    ('Requisito imprescindible de titulación universitaria', True),
    ('Grado obligatorio. FP valorable.', True),
    ('No se requiere grado universitario', False),
    ('Requisitos\nExperiencia en proyectos de ingeniería de mantenimiento.', False),
    ('Requisitos\nConocimiento de procesos de ingeniería.', False),
    ('Requisitos\nNos gustaría que tuvieras alguna de estas titulaciones:\n• Ingeniería Informática.\nInformación adicional', False),
])
def test_education(engine, text, excluded):
    assert engine.evaluate(job(text)).excluded is excluded


def test_education_points(engine):
    assert engine.evaluate(job('DAW')).score_breakdown['education'] == 20
    assert engine.evaluate(job('FP Superior')).score_breakdown['education'] == 20
    assert engine.evaluate(job('Grado o equivalente')).score_breakdown['education'] == 15


@pytest.mark.parametrize('place,mode,text,excluded', [
    ('Sevilla', 'Presencial', '', False), ('Dos Hermanas', 'Híbrido', '', False),
    ('Alcalá de Guadaíra', 'Presencial', '', False), ('Écija', 'Híbrido', '', False),
    ('El Palmar de Troya', 'Presencial', '', False), ('Cartuja / Sevilla TechPark', 'Híbrido', '', False),
    ('Madrid', 'Presencial', '', True), ('Málaga', 'Híbrido', '', True),
    ('Cádiz', 'Presencial', '', True), ('Huelva', 'Presencial', '', True), ('Córdoba', 'Presencial', '', True),
    ('Madrid', 'Remoto', '100% remoto España', False), ('Remoto España', None, '', False),
    ('España', 'Remoto', '', False), (None, None, '', True),  # Fase 3.1: sin ubicación se excluye.
    ('Madrid', None, 'Modelo híbrido en Madrid', True),
    ('Madrid', None, '4 días presencial en Getafe y 1 en remoto', True),
    ('London', 'Remoto', 'Remote UK only', True),
    ('Madrid', 'Remoto', '100% remoto España. Formación presencial opcional.', False),
    ('Aguadulce, Almería', 'Presencial', '', True),
])
def test_location(engine, place, mode, text, excluded):
    result = engine.evaluate(job(text, location=place, modality=mode))
    assert result.excluded is excluded, result.to_dict()


def test_optional_and_mandatory_requirements(engine):
    assert not engine.evaluate(job('Docker valorable')).unmet_requirements
    assert not engine.evaluate(job('Java imprescindible')).unmet_requirements
    result = engine.evaluate(job('Inglés C1 imprescindible'))
    assert len(result.unmet_requirements) == 1 and not result.excluded
    assert result.score_breakdown['penalties'] == -22
    assert not engine.evaluate(job('Inglés C1 valorable')).penalties
    assert engine.evaluate(job('Inglés B2 obligatorio')).penalties['english_b2'] == 3
    assert engine.evaluate(job('Inglés C1 obligatorio. Francés B2 obligatorio.')).excluded
    assert not engine.evaluate(job('Inglés alto obligatorio')).unmet_requirements


def test_examples_a_to_e(engine):
    a = engine.evaluate(job('Sin experiencia. FP DAW. Java Spring.', title='Junior Developer'))
    b = engine.evaluate(job('5 años de experiencia. Ingeniería obligatoria.', title='Senior Java Developer'))
    c = engine.evaluate(job('Sin experiencia.', title='Application Support Junior'))
    d = engine.evaluate(job('Sin experiencia.', title='Helpdesk N1'))
    e = engine.evaluate(job('0-1 años. Python. 100% remoto España.', title='Backend Developer', location='Madrid', modality='Remoto'))
    assert a.score >= 90
    assert b.excluded and b.score == 0
    assert c.score >= 75 and c.score < a.score
    assert d.score >= 60 and d.score < c.score
    assert not e.excluded and e.score >= 75


@pytest.mark.parametrize('score,label', [(0,'Ocultar'),(39,'Ocultar'),(40,'Baja prioridad'),(59,'Baja prioridad'),
    (60,'Revisar'),(74,'Revisar'),(75,'Muy interesante'),(89,'Muy interesante'),(90,'Candidatura prioritaria'),(100,'Candidatura prioritaria')])
def test_classification_boundaries(score, label):
    assert classify(score) == label
    assert classify(score, True) == 'Excluida'


def test_config_changes_and_determinism(engine):
    example = job('3 años de experiencia. Grado universitario obligatorio.')
    assert engine.evaluate(example).excluded
    profile = deepcopy(load_profile())
    profile.update(max_required_experience_years=5, professional_experience_years=5, university_degree=True)
    result = ScoringEngine(profile).evaluate(example)
    assert not result.excluded
    assert result.to_dict() == ScoringEngine(profile).evaluate(example).to_dict()
    assert result.profile_hash != engine.hash
