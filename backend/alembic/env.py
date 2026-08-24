import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

# 1. Add backend directory to sys.path so 'app' imports work smoothly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 2. Import Base, DATABASE_URL, and models
from app.database import Base, DATABASE_URL
import app.models  # Registers all SQLAlchemy models with Base.metadata

# Convert async/legacy DB URLs to synchronous driver for Alembic execution
SYNC_DATABASE_URL = str(DATABASE_URL)
if SYNC_DATABASE_URL.startswith("postgres://"):
    SYNC_DATABASE_URL = SYNC_DATABASE_URL.replace("postgres://", "postgresql://", 1)
elif SYNC_DATABASE_URL.startswith("postgresql+asyncpg://"):
    SYNC_DATABASE_URL = SYNC_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

# This is the Alembic Config object
config = context.config

# 3. Inject DATABASE_URL into alembic config (escape '%' to prevent ConfigParser interpolation errors)
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL.replace("%", "%%"))

# Setup loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. Set target_metadata so Alembic autogenerate detects your models
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = SYNC_DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        SYNC_DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()