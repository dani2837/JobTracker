import pytest

from app.services.scoring.engine import ScoringEngine


@pytest.mark.parametrize('title,description', [
    ('Delineante', 'Digitalización de planos AutoCAD para redes de telecomunicaciones.'),
    ('Jornada de selección: Instalador de Fibra Óptica', 'Sin experiencia. Formación remunerada.'),
    ('Instalador/a de Telecomunicaciones', 'Instalación de equipos y antenas.'),
    ('Técnico/a de telecomunicación', 'Instalación y mantenimiento de equipos de telecomunicaciones. Trabajos en altura.'),
    ('Servicio Técnico de Telecomunicaciones', 'Soporte técnico de dispositivos de Teleasistencia. Ticketing y actualización de software.'),
    ('Técnico de climatización', 'Mantenimiento de instalaciones. Uso de aplicaciones informáticas.'),
    ('Técnico de mantenimiento industrial', 'Mantenimiento preventivo de maquinaria.'),
    ('Soporte comercial', 'Venta de servicios cloud y software. Gestión de clientes en Salesforce.'),
])
def test_non_it_work_is_excluded_despite_technology_category(title, description):
    result = ScoringEngine().evaluate({'title': title, 'description': description,
        'location': 'Sevilla', 'category': 'Informática y telecomunicaciones'})
    assert result.excluded and result.score == 0
    assert 'role' in result.facts['exclusion_categories']


@pytest.mark.parametrize('title', [
    'Desarrollador/a Full Stack', 'Administrador/a Sistemas Junior', 'Junior IT Support',
    'Helpdesk N1', 'QA Tester', 'Analista SOC N1', 'Soporte de aplicaciones',
    'Profesional Cloud', 'Analista de Datos', 'Consultor tecnológico',
])
def test_it_roles_remain_accepted_in_telecom_company(title):
    result = ScoringEngine().evaluate({'title': title, 'location': 'Sevilla',
        'description': 'Empresa de instalación de fibra óptica y telecomunicaciones. Equipo informático interno.'})
    assert not result.excluded


def test_telecom_technician_with_actual_it_duties_remains_accepted():
    result = ScoringEngine().evaluate({'title': 'Técnico de telecomunicaciones', 'location': 'Sevilla',
        'description': 'Administrar servidores Linux.\nConfigurar redes y bases de datos.\n'
                       'Nuestra empresa tiene instaladores de fibra óptica.'})
    assert not result.excluded
