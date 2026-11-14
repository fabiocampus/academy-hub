"""Ambiente Alembic: URL dagli attributi della configurazione o da ACADEMY_DATABASE_URL.

Il motore è quello dell'app (`crea_motore`): su Lakebase la password è un token OAuth.
Con `ACADEMY_DATABASE_SCHEMA` le migrazioni creano lo schema se manca; il `search_path`
impostato dal motore manda lì le tabelle e anche `alembic_version`.
"""

from alembic import context
from sqlalchemy import pool, text

from academy_hub.config import impostazioni
from academy_hub.db.modelli import Base
from academy_hub.db.motore import crea_motore

config = impostazioni()
url: str = context.config.attributes.get("url") or config.database_url
schema = config.database_schema

if context.is_offline_mode():
    context.configure(
        url=url,
        literal_binds=True,
        target_metadata=Base.metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    motore = crea_motore(config, url, poolclass=pool.NullPool)
    with motore.connect() as connessione:
        if schema is not None:
            # Il nome è validato dalla configurazione (solo [a-z0-9_]).
            connessione.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            connessione.commit()
        context.configure(
            connection=connessione,
            target_metadata=Base.metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    motore.dispose()
