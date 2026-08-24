import sys 
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import Repository, File
from app.ingestion.clone import clone_repo 
from app.ingestion.walk import walk_python_files