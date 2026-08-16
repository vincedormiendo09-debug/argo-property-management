import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# 1. PostgreSQL Connection URL Handler
# Normalize 'postgres://' to 'postgresql://' for SQLAlchemy 2.0+ live cloud database compatibility (e.g. Supabase, Render, Neon, Heroku)
RAW_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:123456@127.0.0.1:5432/argo_dev"
)

if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

# Optional SQL query echo configuration via environment variable (defaults to False in live/production)
SQL_ECHO = os.getenv("SQL_ECHO", "False").lower() in ("true", "1", "t")

# 2. Create Engine with Production Connection Pooling & Auto-Reconnect
engine_kwargs = {"echo": SQL_ECHO}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL Live Database Pool Configuration
    engine_kwargs.update({
        "pool_pre_ping": True,     # Tests connections before using them to prevent dropped/stale socket errors
        "pool_size": 10,           # Number of persistent connection sockets to keep open
        "max_overflow": 20,        # Maximum overflow connections during peak request spikes
        "pool_recycle": 1800       # Recycles connections every 30 minutes to avoid server-side timeouts
    })

engine = create_engine(DATABASE_URL, **engine_kwargs)

# 3. Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 4. SQLAlchemy 2.0 Declarative Base
class Base(DeclarativeBase):
    pass


# 5. Dependency for FastAPI routes to safely acquire and release database sessions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 6. Database schema initialization helper
def init_db():
    """Creates all registered database tables in PostgreSQL if they do not exist."""
    Base.metadata.create_all(bind=engine)