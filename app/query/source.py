from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import File, Function


def resolve_disk_path(repository_id: int, file_path: str) -> Path:
    rel = file_path.replace("\\", "/")
    cloned = Path("data/repos") / str(repository_id) / rel
    if cloned.exists():
        return cloned
    fixture = Path("tests/fixtures/shop") / Path(rel).name
    if fixture.exists():
        return fixture
    return cloned


def load_function_source(function_id: int, repository_id: int, max_lines: int = 40) -> dict | None:
    db = SessionLocal()
    func = db.get(Function, function_id)
    if func is None:
        return None
    file_row = db.get(File, func.file_id)
    if file_row is None:
        return None

    path = file_row.path.replace("\\", "/")
    disk = resolve_disk_path(repository_id, file_row.path)
    snippet = ""
    if disk.exists():
        lines = disk.read_text(encoding="utf-8").splitlines()
        start = max((func.start_line or 1) - 1, 0)
        end = min(func.end_line or start + 1, start + max_lines)
        snippet = "\n".join(lines[start:end])

    return {
        "id": func.id,
        "name": func.name,
        "qualified_name": func.qualified_name or func.name,
        "path": path,
        "start_line": func.start_line,
        "end_line": func.end_line,
        "docstring": func.docstring,
        "snippet": snippet,
    }
