from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.db.models import Base

with create_engine(get_settings().database_url).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
