import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Railway injects DATABASE_URL as the standard Postgres variable.
# CRM_DATABASE_URL takes precedence when set explicitly.
_raw_url = (
    os.environ.get("CRM_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql+psycopg://postgres:postgres@localhost:5432/crm"
)

# Normalize bare postgresql:// and postgres:// (Railway default format, which
# makes SQLAlchemy select the psycopg2 dialect) to postgresql+psycopg:// so
# the installed psycopg3 driver is always used.
DATABASE_URL = (
    _raw_url
    .replace("postgresql://", "postgresql+psycopg://", 1)
    .replace("postgres://", "postgresql+psycopg://", 1)
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
