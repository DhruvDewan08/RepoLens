from app.db.session import SessionLocal
from app.db.models import File, Import


def _posix(path: str) -> str:
    return path.replace("\\", "/")


def _stem(path: str) -> str:
    return _posix(path).split("/")[-1].removesuffix(".py")


def folder_key(path: str, depth: int = 2) -> str:
    """Collapse a file path to a folder prefix for a high-level map."""
    parts = _posix(path).split("/")
    if len(parts) == 1:
        return "(repo root)"
    return "/".join(parts[: min(depth, len(parts) - 1)])


def file_import_edges(repository_id: int) -> list[tuple[str, str]]:
    """File-to-file import edges that resolve to another file in this repo."""
    db = SessionLocal()
    files = db.query(File).filter_by(repository_id=repository_id).all()
    by_stem = {_stem(f.path): f for f in files}
    by_path_stem: dict[str, File] = {}
    for f in files:
        p = _posix(f.path).removesuffix(".py")
        by_path_stem[p] = f
        if "/" in p:
            by_path_stem[p.split("/")[-1]] = f

    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for file_row in files:
        source = _posix(file_row.path)
        imports = db.query(Import).filter_by(source_file_id=file_row.id).all()
        for imp in imports:
            if not imp.target_module:
                continue
            mod = imp.target_module.lstrip(".")
            target = by_stem.get(mod.split(".")[-1])
            if target is None and mod:
                dotted = mod.replace(".", "/")
                target = by_path_stem.get(dotted) or by_path_stem.get(dotted.split("/")[-1])
            if target is None or target.id == file_row.id:
                continue
            dest = _posix(target.path)
            key = (source, dest)
            if key not in seen:
                seen.add(key)
                edges.append(key)

    return sorted(edges)


def folder_import_edges(repository_id: int, depth: int = 2) -> list[tuple[str, str]]:
    collapsed: set[tuple[str, str]] = set()
    for src, dst in file_import_edges(repository_id):
        a, b = folder_key(src, depth), folder_key(dst, depth)
        if a != b:
            collapsed.add((a, b))
    return sorted(collapsed)


def import_edges_for_display(
    repository_id: int, depth: int = 2
) -> tuple[list[tuple[str, str]], str]:
    """
    Returns (edges, level) where level is 'folder' or 'file'.
    Flat repos (all files at root) have no folder-level edges — fall back to files.
    """
    file_edges = file_import_edges(repository_id)
    folder_edges = folder_import_edges(repository_id, depth=depth)
    if folder_edges:
        return folder_edges, "folder"
    if file_edges:
        return file_edges, "file"
    return [], "none"


def list_repo_dir(repository_id: int, prefix: str) -> tuple[list[str], list[str]]:
    """Immediate subfolders and files under prefix (empty prefix = repo root)."""
    db = SessionLocal()
    rows = db.query(File.path).filter_by(repository_id=repository_id).all()
    prefix = _posix(prefix).strip("/")
    dirs: set[str] = set()
    files: list[str] = []

    for (raw,) in rows:
        path = _posix(raw)
        if prefix:
            if path == prefix:
                files.append(path)
                continue
            if not path.startswith(prefix + "/"):
                continue
            rest = path[len(prefix) + 1 :]
        else:
            rest = path
        if "/" in rest:
            dirs.add(rest.split("/", 1)[0])
        else:
            files.append(path)

    return sorted(dirs), sorted(files)


def file_row_by_path(repository_id: int, path: str) -> File | None:
    db = SessionLocal()
    target = _posix(path)
    for row in db.query(File).filter_by(repository_id=repository_id).all():
        if _posix(row.path) == target:
            return row
    return None


ENTRY_FILE_SUFFIXES = (
    "/app.py",
    "/main.py",
    "/wsgi.py",
    "/asgi.py",
    "/__init__.py",
    "/__main__.py",
)


def likely_entry_files(repository_id: int, limit: int = 12) -> list[File]:
    db = SessionLocal()
    files = db.query(File).filter_by(repository_id=repository_id).all()
    hits = []
    for row in files:
        p = "/" + _posix(row.path)
        if p.endswith(ENTRY_FILE_SUFFIXES) or _posix(row.path) in {
            "app.py",
            "main.py",
            "__init__.py",
        }:
            hits.append(row)

    def _rank(row: File) -> tuple[int, str]:
        p = _posix(row.path)
        if p.endswith("app.py") or p.endswith("main.py"):
            return (0, p)
        if p.endswith("wsgi.py") or p.endswith("asgi.py"):
            return (1, p)
        return (2, p)

    hits.sort(key=_rank)
    return hits[:limit]
