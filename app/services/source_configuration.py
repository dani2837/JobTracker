PORTALS = {
    'Emergya': 'https://www.emergya.com/es/trabaja-con-nosotros',
    'Isotrol': 'https://www.isotrol.com/es/careers',
    'Sopra Steria': 'https://careers.soprasteria.es/jobs',
    'Izertis': 'https://jobs.izertis.com/jobs',
    'Indra / Minsait': 'https://careers.indragroup.com/search/?q=&optionsFacetsDD_country=ES',
    'Deloitte': 'https://empleo.es.deloitte.com/search/',
    'Accenture': 'https://www.accenture.com/es-es/careers/jobsearch',
    'Ayesa': 'https://www.ayesa.com/ofertas-trabajo/page/1/',
    'T-Systems': 'https://careers.smartrecruiters.com/T-SystemsIberia',
}
GUADALTEL_URL = 'https://www.guadaltel.com/trabajar-guadaltel/'


def configure_sources(db):
    with db.connect() as connection:
        for name, url in PORTALS.items():
            connection.execute("UPDATE companies SET careers_url=?, source_type='Portal público' WHERE name=?", (url, name))
        connection.execute('''UPDATE companies SET accepts_spontaneous_application=1,
            spontaneous_application_url=?,source_type='Candidatura espontánea' WHERE name='Guadaltel' ''', (GUADALTEL_URL,))
