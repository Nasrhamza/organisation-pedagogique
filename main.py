import os
import sys
from pathlib import Path
from app.db import Database
from app.demo_data import populate_demo_database
from app.activation_ui import request_activation
from app.licensing import LicenceManager
from app.rules import RuleSet
from app.ui import MainWindow

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'TanzimPedagogique'
DB_PATH = DATA_DIR / 'school.db'
RULES_PATH = ROOT / 'config' / 'rules_2026_2027.json'
PUBLIC_KEY_PATH = ROOT / 'config' / 'license_public.pem'

if __name__=='__main__':
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    licence = LicenceManager(DATA_DIR, PUBLIC_KEY_PATH)
    licence_status = licence.validate()
    if not licence_status.valid and not request_activation(licence):
        raise SystemExit(0)
    first_launch = not DB_PATH.exists()
    db=Database(DB_PATH)
    rules=RuleSet(RULES_PATH)
    if first_launch:
        populate_demo_database(db, rules, replace=True, generate=True)
    app=MainWindow(db,rules,ROOT,licence=licence)
    app.mainloop()
