from sqlalchemy import text

from app.db.session import engine
from app.db.models import Base

with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()

Base.metadata.create_all(bind=engine)
print("DB connection OK, tables created.")
