from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


ACK_TEXT = "I confirm I have legal authorization to process this evidence."


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    vault_dir: Path
    database_url: str
    redis_url: str
    bind_host: str
    bind_port: int


def _load_dotenv() -> None:
    """
    Lightweight `.env` loader for local/dev workflows.
    Existing process env vars always win.
    """
    env_path = Path(".env")
    if not env_path.exists() or not env_path.is_file():
        return

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value


def load_settings() -> Settings:
    _load_dotenv()

    data_dir = Path(os.getenv("EVIFORGE_DATA_DIR", "./.eviforge")).resolve()
    vault_dir = Path(os.getenv("EVIFORGE_VAULT_DIR", str(data_dir / "vault"))).resolve()
    database_url = os.getenv("EVIFORGE_DATABASE_URL", f"sqlite:///{(data_dir / 'eviforge.db').as_posix()}")
    redis_url = os.getenv("EVIFORGE_REDIS_URL", "redis://redis:6379/0")

    bind_host = os.getenv("EVIFORGE_BIND_HOST", "127.0.0.1")
    bind_port = int(os.getenv("EVIFORGE_BIND_PORT", "8000"))

    return Settings(
        data_dir=data_dir,
        vault_dir=vault_dir,
        database_url=database_url,
        redis_url=redis_url,
        bind_host=bind_host,
        bind_port=bind_port,
    )

# Rev 21

# Rev 25

# Rev 27

# Rev 35

# Rev 39

# Rev 48

# Rev 49

# Rev 50

# Rev 53

# Rev 62

# Rev 68

# Rev 73

# Rev 79

# Rev 88
