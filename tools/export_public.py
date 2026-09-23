"""Export only the inspected Git index; never recurse over local app data."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from check_publication import ROOT, staged_files


def main():
    files, problems = staged_files()
    if problems:
        raise SystemExit('\n'.join(problems))
    destination = ROOT / 'data' / 'publication' / 'JobTracker-public.zip'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    with ZipFile(temporary, 'w', ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    temporary.replace(destination)
    print(f'Exported {len(files)} inspected files to {destination.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
