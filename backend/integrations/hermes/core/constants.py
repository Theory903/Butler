import os
from pathlib import Path


def get_butler_integration_home() -> Path:
    return Path(os.getenv("BUTLER_INTEGRATION_HOME", os.getenv("HERMES_HOME", Path.home() / ".butler")))


def get_default_butler_integration_root() -> Path:
    native_home = Path.home() / ".butler"
    env_home = os.environ.get("BUTLER_INTEGRATION_HOME", os.environ.get("HERMES_HOME", ""))
    if not env_home:
        return native_home
    env_path = Path(env_home)
    try:
        env_path.resolve().relative_to(native_home.resolve())
        return native_home
    except ValueError:
        pass

    if env_path.parent.name == "profiles":
        return env_path.parent.parent
    return env_path


def get_optional_skills_dir(default: Path | None = None) -> Path:
    override = os.getenv("BUTLER_OPTIONAL_SKILLS", os.getenv("HERMES_OPTIONAL_SKILLS", "")).strip()
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_butler_integration_home() / "optional-skills"


def get_butler_integration_dir(new_subpath: str, old_name: str) -> Path:
    home = get_butler_integration_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath


def display_butler_integration_home() -> str:
    home = get_butler_integration_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


def get_subprocess_home() -> str | None:
    integration_home = os.getenv("BUTLER_INTEGRATION_HOME", os.getenv("HERMES_HOME"))
    if not integration_home:
        return None
    profile_home = os.path.join(integration_home, "home")
    if os.path.isdir(profile_home):
        return profile_home
    return None


VALID_REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")


def parse_reasoning_effort(effort: str) -> dict | None:
    if not effort or not effort.strip():
        return None
    effort = effort.strip().lower()
    if effort == "none":
        return {"enabled": False}
    if effort in VALID_REASONING_EFFORTS:
        return {"enabled": True, "effort": effort}
    return None


def is_termux() -> bool:
    prefix = os.getenv("PREFIX", "")
    return bool(os.getenv("TERMUX_VERSION") or "com.termux/files/usr" in prefix)


_wsl_detected: bool | None = None


def is_wsl() -> bool:
    global _wsl_detected
    if _wsl_detected is not None:
        return _wsl_detected
    try:
        with open("/proc/version", "r") as f:
            _wsl_detected = "microsoft" in f.read().lower()
    except Exception:
        _wsl_detected = False
    return _wsl_detected


_container_detected: bool | None = None


def is_container() -> bool:
    global _container_detected
    if _container_detected is not None:
        return _container_detected
    if os.path.exists("/.dockerenv"):
        _container_detected = True
        return True
    if os.path.exists("/run/.containerenv"):
        _container_detected = True
        return True
    try:
        with open("/proc/1/cgroup", "r") as f:
            cgroup = f.read()
            if "docker" in cgroup or "podman" in cgroup or "/lxc/" in cgroup:
                _container_detected = True
                return True
    except OSError:
        pass
    _container_detected = False
    return False


def get_config_path() -> Path:
    return get_butler_integration_home() / "config.yaml"


def get_skills_dir() -> Path:
    return get_butler_integration_home() / "skills"


def get_env_path() -> Path:
    return get_butler_integration_home() / ".env"


get_hermes_home = get_butler_integration_home
get_default_hermes_root = get_default_butler_integration_root
get_hermes_dir = get_butler_integration_dir
display_hermes_home = display_butler_integration_home


def apply_ipv4_preference(force: bool = False) -> None:
    if not force:
        return

    import socket

    if getattr(socket.getaddrinfo, "_hermes_ipv4_patched", False):
        return

    _original_getaddrinfo = socket.getaddrinfo

    def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0:
            try:
                return _original_getaddrinfo(
                    host, port, socket.AF_INET, type, proto, flags
                )
            except socket.gaierror:
                return _original_getaddrinfo(host, port, family, type, proto, flags)
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    setattr(_ipv4_getaddrinfo, "_hermes_ipv4_patched", True)
    socket.getaddrinfo = _ipv4_getaddrinfo


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"
AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
