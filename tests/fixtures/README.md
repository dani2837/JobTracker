# Fixtures offline

Los adaptadores se prueban con fragmentos de listados y fichas públicas o
respuestas simuladas. Se omiten navegación, analítica, formularios y sesiones.
Las variantes de paginación cambian contadores e identificadores para simular
varias páginas sin consultar Internet.

Los archivos `scoring_regressions.json` contienen requisitos de ofertas para
comprobar casos límite. No contienen IDs locales, estados de candidatura ni
puntuaciones de una búsqueda personal. Las expectativas se calculan sobre el
perfil sintético que crea `tests/conftest.py`, no sobre el perfil de quien usa
la aplicación. Los esquemas SQL históricos permiten probar las migraciones.

Los nombres y enlaces oficiales presentes en otras fixtures son datos públicos
necesarios para comprobar el contrato de los adaptadores; no son recomendaciones
ni un historial de candidaturas.
