import sys
from datetime import datetime, timezone
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import File, Repository
from app.ingestion.clone import clone_repo
from app.ingestion.walk import walk_python_files


def normalize_github_url(url: str) -> str:
    url = url.strip().rstrip("/") #strips whitespace and trailing slashes
    if url.endswith(".git"):
        url = url[: -len(".git")]
    return url


def repo_name_from_url(url: str) -> str: #extracts the repository name from the URL
    return url.split("/")[-1]


def main(url: str, branch: str | None = None) -> None:
    url = normalize_github_url(url)
    db = SessionLocal() #opens a connection to the postgress , using the engine we set up in the db.session.py file 
    repo = None
    try:
        repo = db.query(Repository).filter_by(github_url=url).one_or_none() #check if the repository is already in the database
        if repo is None:
            repo = Repository(
                name=repo_name_from_url(url),
                github_url=url,
                status="indexing",
            )
            if branch:
                repo.branch = branch
            db.add(repo)
        else:
            repo.status = "indexing"
            if branch:
                repo.branch = branch
            db.query(File).filter_by(repository_id=repo.id).delete() #delete all the files for the repository
        db.commit()

        dest = Path("data/repos") / str(repo.id)
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Only pass --branch when the user asked; otherwise git uses the remote default.
        repo.last_commit = clone_repo(url, dest, branch=branch)

        file_count = 0
        for f in walk_python_files(dest):
            db.add(File(repository_id=repo.id, **f))
            file_count += 1

        repo.status = "ready"
        repo.indexed_at = datetime.now(timezone.utc)
        db.commit()

        print(f"indexed '{repo.name}' (repository_id={repo.id}): {file_count} files") #print the repository name and the number of files indexed
    except Exception:
        if repo is not None and repo.id is not None:
            repo.status = "failed"
            db.commit()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2: #check if the user has provided the github url and the branch
        print("Usage: python -m app.ingestion.ingest <github_url> [branch]")
        sys.exit(1)
    optional_branch = sys.argv[2] if len(sys.argv) > 2 else None
    main(sys.argv[1], optional_branch)
