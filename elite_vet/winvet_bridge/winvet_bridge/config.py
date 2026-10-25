"""INI configuration of the bridge.

The config path is given by ``--config`` or the environment variable ``WINVET_BRIDGE_CONFIG``.
Relative paths inside the file are resolved against the directory of the config file.
"""

from __future__ import annotations

import configparser
import datetime as _dt
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_ENV = "WINVET_BRIDGE_CONFIG"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VERIFIED_FILE = PACKAGE_ROOT / "verified.json"
DEFAULT_SCHEMA_BASELINE_FILE = PACKAGE_ROOT / "schema_baseline.json"
SOURCES = ("live", "backup")


class ConfigError(Exception):
    """Invalid or incomplete configuration."""


@dataclass
class FirebirdConfig:
    dsn: str
    user: str
    password: str = field(repr=False)
    fb_client_library: Optional[Path] = None


@dataclass
class OdooConfig:
    url: str
    api_key: str = field(repr=False)
    timeout: float = 60.0
    retries: int = 3


@dataclass
class BridgeConfig:
    firebird: FirebirdConfig
    odoo: Optional[OdooConfig]
    source: str = "live"
    state_file: Path = Path("winvet_bridge_state.json")
    verified_file: Path = DEFAULT_VERIFIED_FILE
    schema_baseline_file: Path = DEFAULT_SCHEMA_BASELINE_FILE
    batch_size: int = 500
    interval_minutes: int = 15
    full_sync_time: _dt.time = _dt.time(3, 0)
    log_file: Optional[Path] = None
    log_level: str = "INFO"
    odoo_error: Optional[str] = None
    #: contract v4: calendar window = today - days_back .. today + days_ahead
    calendar_days_back: int = 1
    calendar_days_ahead: int = 60
    #: service mode (``run``): extra calendar-only run every n minutes (0 = only with the normal run)
    calendar_interval_minutes: int = 5

    def require_odoo(self) -> OdooConfig:
        if self.odoo is None:
            raise ConfigError(self.odoo_error or "Section [odoo] is not configured")
        return self.odoo


def _secret(section: configparser.SectionProxy, key: str, env_key: str, label: str) -> str:
    env_name = section.get(env_key, "").strip()
    if env_name:
        value = os.environ.get(env_name)
        if not value:
            raise ConfigError(f"{label}: environment variable {env_name!r} is not set")
        return value
    value = section.get(key, "").strip()
    if not value:
        raise ConfigError(f"{label}: set either '{key}' or '{env_key}' in [{section.name}]")
    return value


def _path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path)


def resolve_config_path(cli_value: Optional[str]) -> Path:
    value = cli_value or os.environ.get(CONFIG_ENV)
    if not value:
        raise ConfigError(f"No config file: use --config or set {CONFIG_ENV}")
    path = Path(value).expanduser()
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    return path


def load_config(path: Path) -> BridgeConfig:
    parser = configparser.ConfigParser(interpolation=None)
    with open(path, encoding="utf-8") as handle:
        parser.read_file(handle)
    base = Path(path).resolve().parent

    if not parser.has_section("firebird"):
        raise ConfigError("Missing section [firebird]")
    fb = parser["firebird"]
    dsn = fb.get("dsn", "").strip()
    if not dsn:
        raise ConfigError("[firebird] dsn is required")
    lib = fb.get("fb_client_library", "").strip()
    firebird = FirebirdConfig(
        dsn=dsn,
        user=fb.get("user", "SYSDBA").strip() or "SYSDBA",
        password=_secret(fb, "password", "password_env", "Firebird password"),
        fb_client_library=_path(base, lib) if lib else None,
    )

    odoo = None
    odoo_error = None
    if parser.has_section("odoo") and parser["odoo"].get("url", "").strip():
        od = parser["odoo"]
        try:
            odoo = OdooConfig(
                url=od.get("url").strip().rstrip("/"),
                api_key=_secret(od, "api_key", "api_key_env", "Odoo API key"),
                timeout=od.getfloat("timeout", 60.0),
                retries=od.getint("retries", 3),
            )
        except ConfigError as exc:
            odoo_error = str(exc)
    else:
        odoo_error = "Section [odoo] with 'url' is not configured"

    br = parser["bridge"] if parser.has_section("bridge") else parser["DEFAULT"]
    source = br.get("source", "live").strip().lower()
    if source not in SOURCES:
        raise ConfigError(f"[bridge] source must be one of {SOURCES}, got {source!r}")
    batch_size = br.getint("batch_size", 500)
    if not 1 <= batch_size <= 500:
        raise ConfigError("[bridge] batch_size must be between 1 and 500 (contract limit)")
    interval = br.getint("interval_minutes", 15)
    if interval < 1:
        raise ConfigError("[bridge] interval_minutes must be >= 1")
    try:
        full_time = _dt.datetime.strptime(br.get("full_sync_time", "03:00").strip(), "%H:%M").time()
    except ValueError as exc:
        raise ConfigError("[bridge] full_sync_time must be HH:MM") from exc
    calendar_back = br.getint("calendar_days_back", 1)
    calendar_ahead = br.getint("calendar_days_ahead", 60)
    calendar_interval = br.getint("calendar_interval_minutes", 5)
    if not 0 <= calendar_back <= 366 or not 1 <= calendar_ahead <= 731:
        raise ConfigError("[bridge] calendar_days_back must be 0-366 and calendar_days_ahead 1-731")
    if calendar_interval < 0:
        raise ConfigError("[bridge] calendar_interval_minutes must be >= 0")
    log_file = br.get("log_file", "").strip()
    verified = br.get("verified_file", "").strip()
    baseline = br.get("schema_baseline_file", "").strip()

    return BridgeConfig(
        firebird=firebird,
        odoo=odoo,
        odoo_error=odoo_error,
        source=source,
        state_file=_path(base, br.get("state_file", "winvet_bridge_state.json").strip()),
        verified_file=_path(base, verified) if verified else DEFAULT_VERIFIED_FILE,
        schema_baseline_file=_path(base, baseline) if baseline else DEFAULT_SCHEMA_BASELINE_FILE,
        batch_size=batch_size,
        interval_minutes=interval,
        full_sync_time=full_time,
        log_file=_path(base, log_file) if log_file else None,
        log_level=br.get("log_level", "INFO").strip().upper() or "INFO",
        calendar_days_back=calendar_back,
        calendar_days_ahead=calendar_ahead,
        calendar_interval_minutes=calendar_interval,
    )
