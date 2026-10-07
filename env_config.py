"""Loads SMTP credentials from a local .env file (gitignored, never
committed) into os.environ, without needing an extra pip dependency.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")


def load_dotenv():
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def smtp_settings():
    """Returns (settings_dict, missing_keys). settings_dict is only
    complete/usable when missing_keys is empty."""
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD"]
    values = {key: os.environ.get(key, "").strip() for key in required}
    missing = [key for key, value in values.items() if not value]
    values["SMTP_FROM"] = os.environ.get("SMTP_FROM", "").strip() or values["SMTP_USERNAME"]
    return values, missing
