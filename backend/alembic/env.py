import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 1. Add backend directory to sys.path so 'app' imports work smoothly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 2. Import Base, DATABASE_URL, and models
from app.database import Base, DATABASE_URL
import app.models  # Registers property_ models with Base.metadata

# This is the Alembic Config object
config = context.config

# 3. Inject DATABASE_URL from app/database.py into alembic config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Setup loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. Set target_metadata so Alembic autogenerate detects your models
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()