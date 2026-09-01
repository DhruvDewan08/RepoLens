from sqlalchemy import text

from app.db.session import engine
from app.db.models import Base

with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print("Tables dropped and recreated.")