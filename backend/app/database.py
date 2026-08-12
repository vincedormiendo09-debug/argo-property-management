import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# 1. PostgreSQL 17 Connection URL
# Fallback uses 127.0.0.1 (IPv4) to avoid Windows localhost (IPv6 ::1) auth bugs
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:123456@127.0.0.1:5432/argo_dev"
)

# 2. Create Engine (echo=True prints generated SQL queries in terminal for debugging)
engine = create_engine(DATABASE_URL, echo=True)

# 3. Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 4. SQLAlchemy 2.0 Declarative Base
class Base(DeclarativeBase):
    pass


# 5. Dependency for API routes to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()