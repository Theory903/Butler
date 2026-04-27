import os
from pathlib import Path


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


def get_optional_skills_dir(default: Path | None = None) -> Path:
    if optional := os.environ.get("HERMES_OPTIONAL_SKILLS_DIR"):
        return Path(optional)
    if default is not None:
        return default
    return get_hermes_home() / "optional-skills"


def display_hermes_home() -> str:
    home = get_hermes_home()
    try:
        return str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


def apply_ipv4_preference(*, force: bool = False) -> None:
    if force:
        import socket

        _orig_getaddrinfo = socket.getaddrinfo

        def _ipv4_preferred(host, port, family=0, type=0, proto=0, flags=0):
            results = _orig_getaddrinfo(host, port, family, type, proto, flags)
            ipv4 = [r for r in results if r[0] == socket.AF_INET]
            return ipv4 if ipv4 else results

        socket.getaddrinfo = _ipv4_preferred


def parse_reasoning_effort(effort: str) -> dict:
    valid = {"minimal", "low", "medium", "high", "xhigh"}
    normalized = effort.strip().lower()
    if normalized not in valid:
        normalized = "medium"
    return {"effort": normalized}


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"


def is_termux() -> bool:
    return bool(os.getenv("TERMUX_VERSION"))


def is_wsl() -> bool:
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def is_container() -> bool:
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
