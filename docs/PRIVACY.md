# Datos locales y contenido público

El repositorio contiene código, documentación, configuración ficticia y fixtures
para pruebas. No debe contener un historial de búsqueda ni candidaturas.

Fuera de Git:

- Todo `data/`: SQLite, estados, notas, perfiles, capturas, resultados y backups.
- Todo `logs/`: las trazas pueden revelar rutas locales y actividad.
- `app/config/profile.json`: perfil privado opcional.
- Informes `FASE*.md` y scripts manuales ligados a una instalación concreta.
- Fixtures históricos de auditorías personales. Los casos públicos de regresión
  conservan requisitos de ofertas, sin IDs de la base local, estados de
  candidatura ni puntuaciones guardadas.
- Entornos, cachés y archivos de credenciales y claves.

`profile.example.json` es ficticio. Las pruebas crean perfiles temporales con
valores elegidos para cubrir límites del motor. Las ciudades del código y las
pruebas representan el alcance geográfico del producto y casos de prueba, no
la residencia de una persona. Los datos de ejemplo no afirman su formación real.

Los fixtures de adaptadores son fragmentos públicos o respuestas simuladas;
los nombres de empresas y URLs identifican fuentes compatibles. No se
distribuyen páginas completas de investigación ni sesiones de navegación.

`tools/check_publication.py` revisa rutas y contenido **del índice de Git**.
Detecta tipos privados y patrones frecuentes de credenciales, correos y rutas
personales sin imprimir sus valores. Es una comprobación adicional, no una
garantía de detección automática de cualquier dato sensible.

Las exclusiones no borran archivos locales ni purgan un historial existente.
Si se añade un archivo sensible en el futuro, retíralo del índice antes de
publicar. Si ya se publicó, revisa el historial y revoca sus credenciales.
