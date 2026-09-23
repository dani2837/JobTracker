# Publicar el proyecto

## Con Git

Crea en GitHub un repositorio vacío llamado `JobTracker`. Desde este proyecto:

```powershell
git add .
python tools/check_publication.py
git diff --cached --stat
python -m pytest -q
git commit -m "Prepare JobTracker desktop application for publication"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/JobTracker.git
git push -u origin main
```

Sustituye `TU_USUARIO`. Si Git pide configurar la identidad del autor, puedes
usar el correo privado `noreply` de los ajustes de GitHub. No incluyas tokens
en la URL del remoto ni en archivos. Si ya hay remoto, revisa `git remote -v`.
La preparación local no hace push ni configura una identidad de autor por ti.

## Desde el navegador

```powershell
python tools/export_public.py
```

Extrae `data/publication/JobTracker-public.zip` en una carpeta nueva y sube
**su contenido**, incluidos `.github` y `.gitignore`. No subas el ZIP como un
único archivo: GitHub debe mostrar el código. No selecciones la carpeta de
trabajo que contiene tus datos locales.

Descripción sugerida: «Aplicación de escritorio en Python/PySide6 para
seguimiento de ofertas IT, scoring explicable y persistencia local con SQLite».

Temas: `python`, `pyside6`, `sqlite`, `desktop-app`, `job-tracker`, `pytest`.

No se ha elegido una licencia de distribución en nombre del autor. Decide qué
permisos de reutilización deseas conceder antes de añadir una licencia.
