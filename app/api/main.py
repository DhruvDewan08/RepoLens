from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.db.session import SessionLocal
from app.db.models import Repository, File, Function
from app.scripts.ingest import main as ingest_main
from app.scripts.parse import main as parse_main
from app.graph.resolve_calls import resolve_calls
from app.scripts.embed import main as embed_main
from app.graph.traversal import get_callers_bfs, get_callees_bfs
from app.query.context_builder import build_context
from app.query.llm_client import ask_llm

app = FastAPI(title="RepoLens API")


class RepositoryCreate(BaseModel):
    url: str


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


def _run_full_pipeline(url: str):
    ingest_main(url)

    db = SessionLocal()
    repo = db.query(Repository).filter_by(github_url=url.rstrip("/")).first()
    if repo:
        parse_main(repo.id)
        resolve_calls(repo.id)
        embed_main(repo.id)


@app.post("/repositories")
def create_repository(payload: RepositoryCreate, background_tasks: BackgroundTasks):
    db = SessionLocal()
    existing = db.query(Repository).filter_by(github_url=payload.url.rstrip("/")).first()
    if existing:
        return {"repository_id": existing.id, "status": existing.status, "note": "already exists, re-indexing"}

    background_tasks.add_task(_run_full_pipeline, payload.url)
    return {"status": "indexing_started", "url": payload.url}


@app.get("/repositories/{repository_id}")
def get_repository(repository_id: int):
    db = SessionLocal()
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    file_count = db.query(File).filter_by(repository_id=repository_id).count()
    return {
        "id": repo.id,
        "name": repo.name,
        "status": repo.status,
        "file_count": file_count,
        "last_commit": repo.last_commit,
        "indexed_at": repo.indexed_at,
    }


@app.post("/repositories/{repository_id}/ask")
def ask_repository(repository_id: int, payload: AskRequest):
    db = SessionLocal()
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    context = build_context(payload.question, repository_id=repository_id)
    answer = ask_llm(payload.question, context)
    return {"intent": context["intent"], "answer": answer}


@app.get("/functions/{function_id}/impact")
def function_impact(function_id: int, direction: str = "callers", depth: int = 3):
    db = SessionLocal()
    target = db.get(Function, function_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Function not found")

    if direction not in ("callers", "callees"):
        raise HTTPException(status_code=400, detail="direction must be 'callers' or 'callees'")

    results = get_callers_bfs(function_id, depth=depth) if direction == "callers" else get_callees_bfs(function_id, depth=depth)

    return {
        "function": target.qualified_name,
        "direction": direction,
        "depth": depth,
        "results": [{"qualified_name": fn.qualified_name, "depth": hop} for fn, hop in sorted(results, key=lambda r: r[1])],
    }