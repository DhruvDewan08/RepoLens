import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import Repository, File
from app.ingestion.walk import walk_python_files


def main(local_path: str, name: str):
    db = SessionLocal()

    repo = db.query(Repository).filter_by(github_url=f"local:{name}").one_or_none()
    if repo is None:
        repo = Repository(name=name, github_url=f"local:{name}", status="indexing")
        db.add(repo)
    else:
        repo.status = "indexing"
        db.query(File).filter_by(repository_id=repo.id).delete()
    db.commit()

    root = Path(local_path)
    file_count = 0
    for f in walk_python_files(root):
        db.add(File(repository_id=repo.id, **f))
        file_count += 1

    repo.status = "ready"
    db.commit()
    print(f"Ingested local '{name}' (repository_id={repo.id}): {file_count} files")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])