from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import File
from app.embeddings.search import semantic_search
from app.graph.traversal import get_callers_bfs, get_callees_bfs
from app.query.router import classify_intent


def _function_snippet(func, repository_id, max_lines=20):
    db = SessionLocal()
    file_row = db.get(File, func.file_id)

    full_path = Path("data/repos") / str(repository_id) / file_row.path
    if not full_path.exists():
        full_path = Path("tests/fixtures/shop") / file_row.path

    lines = full_path.read_text(encoding="utf-8").splitlines()
    start = func.start_line - 1
    end = min(func.end_line, start + max_lines)
    snippet = "\n".join(lines[start:end])
    return f"{file_row.path}:{func.qualified_name}\n{snippet}"


def build_context(question: str, repository_id: int, top_k: int = 5, depth: int = 2):
    """
    Builds a context packet for the LLM: relevant function snippets
    from semantic search, plus (for impact/flow questions) a graph
    neighborhood of the best-matching function.
    """
    intent = classify_intent(question)

    semantic_results = semantic_search(question, repository_id=repository_id, top_k=top_k)

    function_snippets = [
        _function_snippet(func, repository_id) for func, _distance in semantic_results
    ]

    graph_summary = None
    if intent in ("impact", "flow") and semantic_results:
        target_func, _distance = semantic_results[0]  # best semantic match = likely subject
        callers = get_callers_bfs(target_func.id, depth=depth) #get the callers of the target function
        callees = get_callees_bfs(target_func.id, depth=depth) #get the callees of the target function

        lines = [f"Graph neighborhood for '{target_func.qualified_name}':"] #summary of the graph neighborhood of the target function
        if callers:
            lines.append("Called by (callers):")
            for fn, hop in sorted(callers, key=lambda r: r[1]):
                lines.append(f"  - {fn.qualified_name} (depth {hop})") #add the callers of the target function to the summary
        if callees:
            lines.append("Calls (callees):")
            for fn, hop in sorted(callees, key=lambda r: r[1]): 
                lines.append(f"  - {fn.qualified_name} (depth {hop})")
        graph_summary = "\n".join(lines)

    return {
        "intent": intent, 
        "function_snippets": function_snippets, 
        "graph_summary": graph_summary,
    }