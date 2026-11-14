"""Ambiente Alembic: URL dagli attributi della configurazione o da ACADEMY_DATABASE_URL."""

from alembic import context
from sqlalchemy import create_engine, pool

from academy_hub.config import impostazioni
from academy_hub.db.modelli import Base

url: str = context.config.attributes.get("url") or impostazioni().database_url

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    motore = create_engine(url, poolclass=pool.NullPool)
    with motore.connect() as connessione:
        context.configure(connection=connessione, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    motore.dispose()
