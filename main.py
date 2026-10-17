import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS: dict[str, Any] = {
    "port": 8000,
    "workers": 2,
    "debug": False,
    "log_level": "info",
    "api_key": "",
}

# Only these public configuration keys are exposed by the service.
ALLOWED_KEYS = set(DEFAULTS)
INT_KEYS = {"port", "workers"}
BOOL_KEYS = {"debug"}


def normalize_key(key: str) -> str:
    key = key.strip().lower()
    if key == "num_workers":
        return "workers"
    return key


def parse_value(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if key in INT_KEYS:
        try:
            return int(value.strip())
        except ValueError:
            return value
    if key in BOOL_KEYS:
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return value


def apply_layer(config: dict[str, Any], values: dict[str, Any], prefix: str = "") -> None:
    for raw_key, raw_value in values.items():
        if raw_value is None:
            continue
        key = raw_key
        if prefix:
            if not raw_key.upper().startswith(prefix.upper()):
                continue
            key = raw_key[len(prefix):]
        elif raw_key.upper().startswith("APP_"):
            # APP_-prefixed names are also accepted when loaded from .env.
            key = raw_key[4:]
        key = normalize_key(key)
        if key in ALLOWED_KEYS:
            config[key] = parse_value(key, raw_value)


def load_config(overrides: list[str]) -> dict[str, Any]:
    config = DEFAULTS.copy()

    # Layer 2: config.development.yaml. This file is optional in production.
    yaml_path = BASE_DIR / "config.development.yaml"
    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as file:
            yaml_values = yaml.safe_load(file) or {}
        if isinstance(yaml_values, dict):
            apply_layer(config, yaml_values)

    # Layer 3: .env. NUM_WORKERS is supported as an alias for workers.
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        apply_layer(config, dict(dotenv_values(env_file)))

    # Layer 4: actual process environment variables with APP_ prefix.
    apply_layer(config, dict(os.environ), prefix="APP_")

    # Layer 5: each query override is key=value. Later occurrences win.
    for item in overrides:
        if "=" not in item:
            continue
        raw_key, raw_value = item.split("=", 1)
        key = normalize_key(raw_key)
        if key in ALLOWED_KEYS:
            config[key] = parse_value(key, raw_value)

    # Never return the real API key, regardless of which layer supplied it.
    config["api_key"] = "****"
    return config


app = FastAPI(title="Configuration Precedence Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
def root(set: list[str] = Query(default=[])):
    return load_config(set)


@app.get("/config")
def get_config(set: list[str] = Query(default=[])):
    return load_config(set)


@app.get("/health")
def health():
    return {"status": "ok"}
