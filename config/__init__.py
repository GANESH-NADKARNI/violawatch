import configparser
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.ini"

_cfg = configparser.ConfigParser()
_cfg.read(CONFIG_PATH)

def get(section, key, fallback=None):
    return _cfg.get(section, key, fallback=fallback)

def getint(section, key, fallback=0):
    return _cfg.getint(section, key, fallback=fallback)

def getfloat(section, key, fallback=0.0):
    return _cfg.getfloat(section, key, fallback=fallback)

def getbool(section, key, fallback=False):
    return _cfg.getboolean(section, key, fallback=fallback)

# Convenience exports
DB_HOST     = get("database", "host", "localhost")
DB_PORT     = getint("database", "port", 3306)
DB_USER     = get("database", "user", "root")
DB_PASSWORD = get("database", "password", "")
DB_NAME     = get("database", "database", "violawatch")

CONFIDENCE  = getfloat("detection", "confidence_threshold", 0.45)
FRAME_SKIP  = getint("detection", "frame_skip", 2)
SAVE_SNAPS  = getbool("detection", "save_snapshots", True)
SNAPSHOT_DIR = str(BASE_DIR / get("detection", "snapshot_dir", "web/static/snapshots"))
COOLDOWN    = getint("detection", "cooldown_seconds", 10)

SERVER_HOST  = get("server", "host", "0.0.0.0")
SERVER_PORT  = getint("server", "port", 5000)
UPLOAD_DIR   = str(BASE_DIR / get("server", "upload_folder", "web/static/uploads"))
MAX_UPLOAD   = getint("server", "max_upload_mb", 500)

HELMET_MODEL   = get("models", "helmet_model", "") or None
SEATBELT_MODEL = get("models", "seatbelt_model", "") or None
PLATE_MODEL    = get("models", "plate_model", "") or None

os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
