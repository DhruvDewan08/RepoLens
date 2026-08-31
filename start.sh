#!/bin/bash
set -e
python - <<'PY'
from sqlalchemy import text
from app.db.session import engine
from app.db.models import Base

with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()
Base.metadata.create_all(bind=engine)
print("database ready")
PY

PORT="${PORT:-8501}"
exec streamlit run streamlit_app.py \
  --server.port "$PORT" \
  --server.address 0.0.0.0 \
  --server.headless true
