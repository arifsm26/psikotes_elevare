from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context


# --- TAMBAHKAN BLOK INI ---
import os
import sys
from dotenv import load_dotenv

# Tambahkan direktori /app ke path agar bisa import 'models'
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Arahkan ke file .env di root proyek (../.env)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)

# Impor Base dari models.py
from models import Base
# ---------------------------


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# def run_migrations_online() -> None:
   # 
    
    # --- TAMBAHKAN BLOK INI ---
   # config_section = config.get_section(config.config_ini_section)
   # config_section['DB_USER'] = os.getenv('DB_USER')
   # config_section['DB_PASSWORD'] = os.getenv('DB_PASSWORD')
    # Gunakan nama service docker sebagai host
    #config_section['DB_HOST'] = "mysql_db" 
    #config_section['DB_NAME'] = os.getenv('DB_NAME')
    # ---------------------------




    
# GANTI SELURUH FUNGSI run_migrations_online() DENGAN INI:

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    
    # Ambil konfigurasi dasar dari alembic.ini
    connectable = context.config.attributes.get("connection", None)

    if connectable is None:
        # Bangun URL koneksi secara manual dari variabel lingkungan
        DATABASE_URL = "mysql+pymysql://{user}:{password}@{host}/{db_name}".format(
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            host="mysql_db",  # Nama service dari docker-compose.yml
            db_name=os.getenv("MYSQL_DATABASE"),
        )

        # Buat engine SQLAlchemy
        connectable = engine_from_config(
            context.config.get_section(context.config.config_ini_section),
            url=DATABASE_URL, # <-- Gunakan URL yang baru kita buat
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
