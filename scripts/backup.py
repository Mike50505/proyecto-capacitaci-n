"""Create a consistent SQLite backup and copy uploaded question images."""
from pathlib import Path
import sqlite3,zipfile
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'private/backups'/datetime.now().strftime('%Y%m%d-%H%M%S');folder.mkdir(parents=True)
with sqlite3.connect(ROOT/'private/capacitacion.sqlite3') as source,sqlite3.connect(folder/'capacitacion.sqlite3') as target:source.backup(target)
with zipfile.ZipFile(folder/'imagenes.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for p in (ROOT/'assets/uploads').glob('*'):archive.write(p,p.name)
print(folder)
