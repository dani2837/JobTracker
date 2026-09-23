"""DATOS DE PRUEBA: ofertas ficticias, no vacantes reales."""
import logging
from app.database.db import Database

COMPANIES = ['Accenture','NTT DATA','Deloitte','Emergya','Isotrol','Ayesa','Sopra Steria',
             'Indra / Minsait','Tier1','Soltel','Guadaltel','T-Systems','GMV','Izertis','Viewnext']
TITLES = ['Junior Java Developer','Junior Software Developer','Técnico de Sistemas Junior',
          'Backend Developer','Frontend Developer Junior','QA Tester Junior','Application Support Junior',
          'Técnico IT','Helpdesk N1','Full Stack Junior','Consultor Tecnológico Junior',
          'Desarrollador Python Junior','Soporte Linux Junior','Desarrollador .NET Junior',
          'QA Automation Junior','Programador Java Junior','Técnico de Redes Junior','Desarrollador React Junior']


def seed_database(db: Database) -> None:
    with db.connect() as connection:
        # Transacción única para no dejar datos parciales tras un inicio interrumpido.
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("SELECT 1 FROM metadata WHERE key='seed_v1'").fetchone():
            return
        for name in COMPANIES:
            connection.execute('INSERT OR IGNORE INTO companies(name) VALUES (?)', (name,))
        for index, title in enumerate(TITLES):
            company_id = connection.execute('SELECT id FROM companies WHERE name=?', (COMPANIES[index % 15],)).fetchone()[0]
            connection.execute('''INSERT OR IGNORE INTO jobs
                (external_id,title,company_id,location,modality,description,score,published_date,is_test_data,source_name)
                VALUES (?,?,?,?,?,?,?,?,1,'Datos de prueba')''',
                (f'demo-{index+1:03}', title, company_id,
                 ['Sevilla','Dos Hermanas','Alcalá de Guadaíra','Remoto España'][index % 4],
                 'Remoto' if index % 4 == 3 else ['Presencial','Híbrido','Remoto'][index % 3],
                 f'DATOS DE PRUEBA — Oferta ficticia de {title}.\n\n'
                 'Participarás en proyectos IT con un equipo de desarrollo y soporte. '
                 'Se valoran conocimientos básicos, capacidad de aprendizaje y trabajo en equipo.\n\n'
                 'Esta descripción sirve únicamente para comprobar JobTracker.',
                 [98,94,91,90,89,85,81,78,75,74,70,65,60,59,55,49,45,40][index],
                 f'2026-09-{1+index % 7:02}'))
        connection.execute("INSERT INTO metadata VALUES ('seed_v1','complete')")
    logging.getLogger(__name__).info('Seed inicial: 15 empresas y 18 ofertas de prueba')
