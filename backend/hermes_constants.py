from pathlib import Path
import os

def get_hermes_home() -> Path:
    if hermes_home := os.environ.get("HERMES_HOME"):
        return Path(hermes_home)
    return Path.home() / ".butler"

def get_hermes_dir(new_subpath: str, old_name: str) -> Path:
    home = get_hermes_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath

def get_config_path() -> Path:
    return get_hermes_home() / "config.yaml"

def get_skills_dir() -> Path:
    return get_hermes_home() / "skills"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"

def is_termux() -> bool:
    return bool(os.getenv("TERMUX_VERSION"))

def is_wsl() -> bool:
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False

def is_container() -> bool:
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
