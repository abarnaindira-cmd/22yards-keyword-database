import os
import urllib.parse
from pathlib import Path
import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "marketlens")

def ensure_mysql_database_exists():
    """Ensure the target MySQL database exists before SQLAlchemy attempts to connect."""
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            autocommit=True
        )
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        connection.close()
        return True
    except Exception as e:
        print(f"[Database Error] MySQL database initialization check failed: {e}")
        raise e

# Ensure target MySQL database exists
ensure_mysql_database_exists()

# Percent-encode password to handle special characters (e.g., '@') safely in database URL
ENCODED_PASSWORD = urllib.parse.quote_plus(DB_PASSWORD)

# Build MySQL Connection URL
MYSQL_DATABASE_URL = f"mysql+pymysql://{DB_USER}:{ENCODED_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Initialize MySQL Engine exclusively (No SQLite Fallback)
engine = create_engine(
    MYSQL_DATABASE_URL,
    pool_recycle=3600,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI dependency yielding database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create database tables in MySQL if they do not exist."""
    import app.models.keyword  # noqa: F401 (Import models so Base.metadata registers tables)
    import app.models.product  # noqa: F401
    import app.models.competitor  # noqa: F401
    Base.metadata.create_all(bind=engine)

def test_db_connection():
    """Check database connectivity and return status dict."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            return {
                "status": "connected",
                "database_type": "MySQL",
                "database_name": DB_NAME,
                "host": f"{DB_HOST}:{DB_PORT}",
                "user": DB_USER,
                "test_query_result": result
            }
    except Exception as e:
        return {
            "status": "error",
            "database_type": "MySQL",
            "database_name": DB_NAME,
            "error_details": str(e)
        }
