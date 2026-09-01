import graphviz
import streamlit as st

from sqlalchemy import or_
from app.db.models import File, Function, Repository
from app.db.session import SessionLocal
from app.graph.architecture import (
    file_import_edges,
    file_row_by_path,
    import_edges_for_display,
    likely_entry_files,
    list_repo_dir,
)
from app.graph.resolve_calls import resolve_calls
from app.graph.traversal import get_callees_bfs, get_callers_bfs
from app.query.context_builder import build_context
from app.query.llm_client import ask_llm
from app.query.source import load_function_source
from app.scripts.embed import main as embed_main
from app.scripts.ingest import main as ingest_main
from app.scripts.parse import main as parse_main

st.set_page_config(page_title="RepoLens", layout="wide")
st.title("RepoLens")
st.caption("Program-structure analysis: AST, call graph, hybrid retrieval.")

MAX_ARCH_DRAW = 40
MAX_FUNC_DROPDOWN = 80


def _browse_prefix_key(key_prefix: str, repository_id: int) -> str:
    return f"{key_prefix}_prefix_{repository_id}"


def _browse_file_key(key_prefix: str, repository_id: int) -> str:
    return f"{key_prefix}_file_{repository_id}"


def render_function_picker(
    repository_id: int,
    function_count: int,
    *,
    key_prefix: str,
    help_text: str | None = None,
    compact: bool = False,
) -> int | None:
    """Pick a function: search, optional folder browse, entry-file shortcuts."""
    if function_count == 0:
        st.info("No functions parsed yet.")
        return None

    if help_text and not compact:
        st.caption(help_text)

    prefix_key = _browse_prefix_key(key_prefix, repository_id)
    file_key = _browse_file_key(key_prefix, repository_id)
    if prefix_key not in st.session_state:
        st.session_state[prefix_key] = ""
    if file_key not in st.session_state:
        st.session_state[file_key] = ""

    selected_func_id: int | None = None

    def _browse_block() -> int | None:
        prefix = st.session_state[prefix_key]
        pinned_file = st.session_state[file_key]

        crumbs = [("(root)", "")]
        if prefix:
            acc: list[str] = []
            for part in prefix.split("/"):
                acc.append(part)
                crumbs.append((part, "/".join(acc)))
        crumb_cols = st.columns(min(len(crumbs), 6))
        for i, (label, value) in enumerate(crumbs):
            if crumb_cols[i].button(label, key=f"{key_prefix}-crumb-{repository_id}-{i}"):
                st.session_state[prefix_key] = value
                st.session_state[file_key] = ""
                st.rerun()

        dirs, files_here = list_repo_dir(repository_id, prefix)
        if dirs:
            dir_pick = st.selectbox(
                "Folder",
                ["—"] + dirs,
                key=f"{key_prefix}-dir-pick-{repository_id}",
            )
            if dir_pick != "—":
                child = f"{prefix}/{dir_pick}" if prefix else dir_pick
                if st.button("Open folder", key=f"{key_prefix}-open-dir"):
                    st.session_state[prefix_key] = child
                    st.session_state[file_key] = ""
                    st.rerun()

        if not files_here:
            return None

        file_index = files_here.index(pinned_file) if pinned_file in files_here else 0
        selected_file = st.selectbox(
            "File",
            files_here,
            index=file_index,
            key=f"{key_prefix}-file-{repository_id}",
        )
        st.session_state[file_key] = selected_file

        row = file_row_by_path(repository_id, selected_file)
        if not row:
            return None
        fns = (
            SessionLocal()
            .query(Function)
            .filter_by(file_id=row.id)
            .order_by(Function.start_line)
            .all()
        )
        if not fns:
            return None
        labels = {f"{fn.qualified_name}": fn.id for fn in fns}
        pick = st.selectbox(
            "Function",
            list(labels.keys()),
            key=f"{key_prefix}-fn-{repository_id}-{selected_file}",
        )
        return labels[pick]

    entries = likely_entry_files(repository_id)
    if entries:
        label = "Quick picks" if compact else "Likely entry files"
        st.caption(label)
        cols = st.columns(min(len(entries), 4))
        for i, row in enumerate(entries[:8]):
            path = row.path.replace("\\", "/")
            with cols[i % len(cols)]:
                if st.button(path.split("/")[-1], key=f"{key_prefix}-entry-{row.id}", help=path):
                    st.session_state[prefix_key] = "/".join(path.split("/")[:-1])
                    st.session_state[file_key] = path
                    st.rerun()

    if function_count <= MAX_FUNC_DROPDOWN:
        pairs = search_functions(repository_id, "", total_count=function_count)
        if pairs:
            labels = {loc_label(fn, fr): fn.id for fn, fr in pairs}
            pick = st.selectbox(
                "Function",
                sorted(labels.keys()),
                key=f"{key_prefix}-all-funcs",
            )
            selected_func_id = labels[pick]
    else:
        q = st.text_input(
            "Find function",
            placeholder="name, file path, or short description",
            key=f"{key_prefix}-find",
        )
        if q.strip():
            pairs = search_functions(repository_id, q, total_count=function_count)
            if pairs:
                labels = {loc_label(fn, fr): fn.id for fn, fr in pairs}
                pick = st.selectbox("Matches", sorted(labels.keys()), key=f"{key_prefix}-text-pick")
                selected_func_id = labels[pick]
            else:
                from app.embeddings.search import semantic_search

                hits = semantic_search(q, repository_id=repository_id, top_k=8)
                if hits:
                    labels = {}
                    db = SessionLocal()
                    for fn, _dist in hits:
                        file_row = db.get(File, fn.file_id)
                        if file_row:
                            path = file_row.path.replace("\\", "/")
                            labels[f"{fn.qualified_name} ({path})"] = fn.id
                    pick = st.selectbox("Matches", sorted(labels.keys()), key=f"{key_prefix}-sem-pick")
                    selected_func_id = labels[pick]
                else:
                    st.caption("No matches.")

        with st.expander("Browse folders", expanded=False):
            browsed = _browse_block()
            if browsed is not None:
                selected_func_id = browsed

    if not compact:
        st.divider()
        st.markdown("**Or search**")
        search_col, semantic_col = st.columns(2)
        with search_col:
            text_q = st.text_input("Name or path", key=f"{key_prefix}-text-search")
        with semantic_col:
            semantic_q = st.text_input("Describe it", key=f"{key_prefix}-semantic-search")
        if text_q:
            pairs = search_functions(repository_id, text_q, total_count=function_count)
            if pairs:
                labels = {loc_label(fn, fr): fn.id for fn, fr in pairs}
                selected_func_id = labels[
                    st.selectbox("Text matches", sorted(labels.keys()), key=f"{key_prefix}-text-pick-full")
                ]
        elif semantic_q:
            from app.embeddings.search import semantic_search

            hits = semantic_search(semantic_q, repository_id=repository_id, top_k=10)
            if hits:
                labels = {}
                db = SessionLocal()
                for fn, dist in hits:
                    file_row = db.get(File, fn.file_id)
                    if file_row:
                        path = file_row.path.replace("\\", "/")
                        labels[f"{fn.qualified_name}  ({path})  d={dist:.3f}"] = fn.id
                selected_func_id = labels[
                    st.selectbox("Semantic matches", sorted(labels.keys()), key=f"{key_prefix}-semantic-pick-full")
                ]

        st.markdown("**Browse folders**")
        browsed = _browse_block()
        if browsed is not None:
            selected_func_id = browsed

    return selected_func_id


def get_all_repositories():
    db = SessionLocal()
    return db.query(Repository).all()


def run_full_pipeline(url: str):
    ingest_main(url)
    db = SessionLocal()
    repo = db.query(Repository).filter_by(github_url=url.rstrip("/")).first()
    parse_main(repo.id)
    resolve_calls(repo.id)
    embed_main(repo.id)
    return repo.id


def search_functions(repository_id: int, query: str, *, total_count: int, limit: int = MAX_FUNC_DROPDOWN):
    """Load a small slice of functions. Never pull an entire Flask repo into the UI."""
    db = SessionLocal()
    q = (
        db.query(Function, File)
        .join(File, Function.file_id == File.id)
        .filter(File.repository_id == repository_id)
    )
    text = (query or "").strip()
    if text:
        like = f"%{text}%"
        q = q.filter(
            or_(
                Function.name.ilike(like),
                Function.qualified_name.ilike(like),
                File.path.ilike(like),
            )
        )
    elif total_count > limit:
        return []
    return q.order_by(Function.qualified_name).limit(limit).all()


def load_functions_by_ids(ids: list[int]) -> dict:
    if not ids:
        return {}
    db = SessionLocal()
    rows = (
        db.query(Function, File)
        .join(File, Function.file_id == File.id)
        .filter(Function.id.in_(ids))
        .all()
    )
    return {fn.id: (fn, file_row) for fn, file_row in rows}


def loc_label(func: Function, file_row: File) -> str:
    path = file_row.path.replace("\\", "/")
    start = func.start_line or "?"
    end = func.end_line or "?"
    return f"{func.qualified_name or func.name}  ({path}:{start}–{end})"


def render_inspector(function_id: int, repository_id: int) -> None:
    data = load_function_source(function_id, repository_id)
    if data is None:
        st.warning("Function not found.")
        return

    st.markdown(f"**{data['qualified_name']}**")
    st.code(f"{data['path']}:{data['start_line']}–{data['end_line']}", language=None)
    if data.get("docstring"):
        st.caption(data["docstring"])
    if data["snippet"]:
        st.code(data["snippet"], language="python")
    else:
        st.info("Source file not found on disk.")

    callers = get_callers_bfs(function_id, depth=1)
    callees = get_callees_bfs(function_id, depth=1)
    if callers:
        st.markdown("**Direct callers**")
        for fn, _hop in callers:
            st.write(f"- `{fn.qualified_name}`")
    if callees:
        st.markdown("**Direct callees**")
        for fn, _hop in callees:
            st.write(f"- `{fn.qualified_name}`")


with st.sidebar:
    st.header("Repositories")
    with st.form("index_form"):
        new_url = st.text_input("GitHub URL")
        submitted = st.form_submit_button("Index repository")
        if submitted and new_url:
            with st.spinner("Cloning, parsing, resolving, embedding…"):
                new_id = run_full_pipeline(new_url)
            st.success(f"Indexed as repository_id={new_id}")

    repos = get_all_repositories()
    if not repos:
        st.info("No repositories indexed yet.")
        st.stop()

    repo_options = {f"{r.name} (id={r.id}, {r.status})": r.id for r in repos}
    selected_label = st.selectbox("Active repository", list(repo_options.keys()))
    repository_id = repo_options[selected_label]

db = SessionLocal()
active_repo = db.get(Repository, repository_id)
file_count = db.query(File).filter_by(repository_id=repository_id).count()
function_count = (
    db.query(Function).join(File).filter(File.repository_id == repository_id).count()
)

st.caption(
    f"**{active_repo.name}** — {active_repo.status} — "
    f"{file_count} files, {function_count} functions"
)

tab_chat, tab_impact, tab_arch, tab_browse = st.tabs(
    ["Chat", "Impact", "File graph", "Functions"]
)

with tab_chat:
    st.subheader("Ask about this repository")
    st.caption("You do not need to know names. Start with an overview question.")
    question = st.text_input(
        "Question",
        placeholder="What is the structure of this project? What are the main packages?",
    )
    col_a, col_b = st.columns(2)
    run_overview = col_a.button("Summarize this repo", key="ask_overview")
    run_ask = col_b.button("Ask", key="ask_button")
    if run_overview:
        question = (
            "Give a high-level overview of this codebase: main packages/folders, "
            "what they seem responsible for, and likely entry points. "
            "Cite file paths from the context."
        )
    if (run_ask or run_overview) and question:
        with st.spinner("Retrieving context and generating answer…"):
            context = build_context(question, repository_id=repository_id)
            try:
                answer = ask_llm(question, context)
            except RuntimeError as exc:
                st.error(str(exc))
                st.stop()
        st.markdown(f"Intent: `{context['intent']}`")
        st.markdown("### Answer")
        st.write(answer)
        with st.expander("Grounding context"):
            if context.get("graph_summary"):
                st.text(context["graph_summary"])
            for snippet in context["function_snippets"]:
                st.code(snippet, language="python")

with tab_impact:
    st.subheader("Impact analysis")
    st.caption("Who calls this function — and what does it call? (resolved edges only)")

    selected_func_id = render_function_picker(
        repository_id,
        function_count,
        key_prefix="impact",
        compact=True,
    )

    if selected_func_id is not None:
        st.divider()
        ctrl1, ctrl2 = st.columns(2)
        with ctrl1:
            direction = st.radio(
                "Show",
                ["callers", "callees"],
                horizontal=True,
                key="impact_dir",
                format_func=lambda x: "Who calls this" if x == "callers" else "What this calls",
            )
        with ctrl2:
            depth = st.slider("Hops", 1, 5, 3, key="impact_depth")

        results = (
            get_callers_bfs(selected_func_id, depth=depth)
            if direction == "callers"
            else get_callees_bfs(selected_func_id, depth=depth)
        )

        col_graph, col_src = st.columns([1.1, 1])
        with col_graph:
            if not results:
                st.info("No resolved links at this depth.")
            else:
                extra_ids = [selected_func_id] + [fn.id for fn, _hop in results]
                func_by_id = load_functions_by_ids(extra_ids)
                target_fn, target_file = func_by_id[selected_func_id]
                dot = graphviz.Digraph()
                dot.attr(rankdir="TB")
                tpath = target_file.path.replace("\\", "/")
                dot.node(
                    str(selected_func_id),
                    label=f"{target_fn.qualified_name}\\n{tpath}:{target_fn.start_line}",
                    style="filled",
                    fillcolor="lightblue",
                )
                for fn, hop in results:
                    fid = fn.id
                    _, file_row = func_by_id[fid]
                    path = file_row.path.replace("\\", "/")
                    dot.node(str(fid), label=f"{fn.qualified_name}\\n{path}:{fn.start_line}")
                    if direction == "callers":
                        dot.edge(str(fid), str(selected_func_id), label=f"{hop}")
                    else:
                        dot.edge(str(selected_func_id), str(fid), label=f"{hop}")
                st.graphviz_chart(dot)

                with st.expander(f"{len(results)} related functions"):
                    for fn, hop in sorted(results, key=lambda r: r[1]):
                        st.write(f"- `{fn.qualified_name}` (hop {hop})")

        with col_src:
            render_inspector(selected_func_id, repository_id)

with tab_arch:
    st.subheader("Architecture map")
    st.write(
        "**Folders** groups imports by directory. **Files** shows individual file links "
        "(use a path filter on large repos like Flask)."
    )
    view = st.radio("View", ["Folders (overview)", "Files (zoom in)"], horizontal=True)

    if view.startswith("Folders"):
        depth = st.slider("Folder depth", 1, 3, 2, key="arch_folder_depth")
        edges, level = import_edges_for_display(repository_id, depth=depth)
        nodes = sorted({p for e in edges for p in e})
        if level == "folder":
            st.caption(f"{len(nodes)} folders, {len(edges)} import links between folders")
        elif level == "file":
            st.caption(
                f"{len(nodes)} files, {len(edges)} import links — "
                "flat layout (all files at repo root), showing file-level graph"
            )
        else:
            st.caption("0 resolved import links")

        if not edges:
            st.info(
                "No file-to-file imports could be resolved. "
                "Only `from x import y` where `y` maps to another file in this repo counts. "
                "Stdlib and third-party imports are ignored."
            )
        elif len(nodes) > MAX_ARCH_DRAW:
            st.warning("Too wide — switch to **Files** and add a path filter (e.g. `src/flask`).")
            for src, dst in edges[:40]:
                st.write(f"- `{src}` → `{dst}`")
        else:
            dot = graphviz.Digraph()
            dot.attr(rankdir="LR")
            for name in nodes:
                dot.node(name, label=name)
            for src, dst in edges:
                dot.edge(src, dst)
            st.graphviz_chart(dot)
    else:
        file_edges = file_import_edges(repository_id)
        st.caption(f"{len(file_edges)} resolved file-to-file import edges in this repo")
        arch_q = st.text_input(
            "Path contains",
            placeholder="e.g. src/flask   or   checkout",
            key="arch_filter",
        )
        hide_tests = st.checkbox("Hide tests / docs / examples", value=True, key="arch_hide")
        auto_small = file_count <= 15 and not arch_q
        draw = st.button("Draw file graph", key="arch_draw") or auto_small

        if not draw:
            st.info(
                "Click **Draw file graph**, or type a filter. "
                "Flask: try `src/flask` with tests/examples hidden."
            )
        else:
            edges = file_import_edges(repository_id)

            def _skip_path(p: str) -> bool:
                pl = p.replace("\\", "/").lower()
                if not hide_tests:
                    return False
                return any(x in pl for x in ("/test", "tests/", "/docs/", "examples/", "/doc/"))

            filtered_edges = []
            q = (arch_q or "").strip().lower()
            for src, dst in edges:
                if _skip_path(src) or _skip_path(dst):
                    continue
                if q and q not in src.lower() and q not in dst.lower():
                    continue
                filtered_edges.append((src, dst))

            nodes = sorted({p for e in filtered_edges for p in e})
            st.caption(f"{len(filtered_edges)} edges · {len(nodes)} files")

            if not q and len(nodes) > MAX_ARCH_DRAW:
                st.info(f"Too many files ({len(nodes)}). Add a path filter.")
            elif not filtered_edges:
                st.info("No file-to-file imports match.")
            elif len(nodes) > MAX_ARCH_DRAW:
                st.warning("Narrow the filter.")
                for src, dst in filtered_edges[:40]:
                    st.write(f"- `{src}` → `{dst}`")
            else:
                with st.spinner("Rendering graph…"):
                    dot = graphviz.Digraph()
                    dot.attr(rankdir="LR")
                    for path in nodes:
                        dot.node(path, label=path)
                    for src, dst in filtered_edges:
                        dot.edge(src, dst)
                    st.graphviz_chart(dot)

with tab_browse:
    st.subheader("Functions")
    st.caption("Browse or search, then read the source below.")

    picked_id = render_function_picker(
        repository_id,
        function_count,
        key_prefix="browse",
        compact=True,
    )
    if picked_id is not None:
        st.divider()
        render_inspector(picked_id, repository_id)

