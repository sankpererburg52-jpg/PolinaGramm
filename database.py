import os
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# .env (проще всего задать переменные окружения в systemd/docker)
def _load_env():
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./polinagram.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
CODE_TTL = int(os.getenv("CODE_TTL_SECONDS", "300"))
DEV_RETURN_CODE = os.getenv("DEV_RETURN_CODE", "true").lower() == "true"

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
