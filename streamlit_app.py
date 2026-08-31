import graphviz
import streamlit as st

from sqlalchemy import or_
from app.db.models import File, Function, Repository
from app.db.session import SessionLocal
from app.graph.architecture import (
    file_import_edges,
    file_row_by_path,
    folder_import_edges,
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
            answer = ask_llm(question, context)
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
    st.write(
        "Uses resolved call-graph edges. Unresolved calls (stdlib, constructors) are omitted."
    )

    if function_count == 0:
        st.info("No functions parsed yet.")
    else:
        impact_q = st.text_input(
            "Search functions",
            placeholder="checkout  or  src/flask/app.py",
            key="impact_search",
        )
        impact_pairs = search_functions(
            repository_id, impact_q, total_count=function_count
        )
        if not impact_q and function_count > MAX_FUNC_DROPDOWN:
            st.info(
                f"{function_count} functions in this repo. Type a name or path to pick one."
            )
        elif not impact_pairs and impact_q:
            st.info("No matches.")

        if not impact_pairs:
            selected_func_id = None
        else:
            labels = {loc_label(fn, file_row): fn.id for fn, file_row in impact_pairs}
            selected_name = st.selectbox("Function", sorted(labels.keys()), key="impact_func")
            selected_func_id = labels[selected_name]

        if selected_func_id is not None:
            depth = st.slider("Depth", min_value=1, max_value=5, value=3)
            direction = st.radio("Direction", ["callers", "callees"], horizontal=True)

            col_graph, col_src = st.columns([1.2, 1])

            with col_graph:
                if st.button("Analyze"):
                    st.session_state["impact_target"] = selected_func_id
                    st.session_state["impact_direction"] = direction
                    results = (
                        get_callers_bfs(selected_func_id, depth=depth)
                        if direction == "callers"
                        else get_callees_bfs(selected_func_id, depth=depth)
                    )
                    st.session_state["impact_results"] = [
                        (fn.id, hop) for fn, hop in results
                    ]
                    st.session_state["inspect_id"] = selected_func_id

                target_id = st.session_state.get("impact_target")
                stored = st.session_state.get("impact_results")
                stored_dir = st.session_state.get("impact_direction", direction)

                if target_id and stored is not None:
                    extra_ids = [target_id] + [fid for fid, _hop in stored]
                    func_by_id = load_functions_by_ids(extra_ids)
                    target_fn, target_file = func_by_id.get(target_id, (None, None))
                    if target_fn is None:
                        st.warning("Selected function is not in this repository.")
                    elif not stored:
                        st.info("No related functions on resolved edges.")
                    else:
                        dot = graphviz.Digraph()
                        dot.attr(rankdir="TB")
                        tpath = target_file.path.replace("\\", "/")
                        dot.node(
                            str(target_id),
                            label=f"{target_fn.qualified_name}\\n{tpath}:{target_fn.start_line}",
                            style="filled",
                            fillcolor="lightblue",
                        )
                        for fid, hop in stored:
                            fn, file_row = func_by_id[fid]
                            path = file_row.path.replace("\\", "/")
                            dot.node(
                                str(fid),
                                label=f"{fn.qualified_name}\\n{path}:{fn.start_line}",
                            )
                            if stored_dir == "callers":
                                dot.edge(str(fid), str(target_id), label=f"d{hop}")
                            else:
                                dot.edge(str(target_id), str(fid), label=f"d{hop}")
                        st.graphviz_chart(dot)

                        st.markdown("**Neighborhood** (select one to open source)")
                        options = {
                            loc_label(func_by_id[fid][0], func_by_id[fid][1])
                            + f"  depth {hop}": fid
                            for fid, hop in sorted(stored, key=lambda r: r[1])
                        }
                        inspect_label = st.selectbox(
                            "Open in inspector",
                            ["(target function)"] + list(options.keys()),
                        )
                        if inspect_label == "(target function)":
                            st.session_state["inspect_id"] = target_id
                        else:
                            st.session_state["inspect_id"] = options[inspect_label]

            with col_src:
                st.markdown("**Source**")
                inspect_id = st.session_state.get("inspect_id", selected_func_id)
                render_inspector(inspect_id, repository_id)

with tab_arch:
    st.subheader("Architecture map")
    st.write(
        "**Folders** is the overview (no names required). "
        "**Files** is a zoom-in after you pick a path."
    )
    view = st.radio("View", ["Folders (overview)", "Files (zoom in)"], horizontal=True)

    if view.startswith("Folders"):
        depth = st.slider("Folder depth", 1, 3, 2)
        edges = folder_import_edges(repository_id, depth=depth)
        nodes = sorted({p for e in edges for p in e})
        st.caption(f"{len(nodes)} folders, {len(edges)} import links between folders")
        if not edges:
            st.info("Not enough resolved imports to build a folder map.")
        elif len(nodes) > MAX_ARCH_DRAW:
            st.warning("Still too wide — lower folder depth.")
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
            st.write("Open **Functions** and click a folder name from this map to drill in.")
    else:
        st.write("Optional path filter, then Draw. Leave empty only for small repos.")
        arch_q = st.text_input(
            "Path contains",
            placeholder="e.g. src/flask   or   checkout",
            key="arch_filter",
        )
        hide_tests = st.checkbox("Hide tests / docs / examples", value=True, key="arch_hide")
        draw = st.button("Draw file graph", key="arch_draw")

        if not draw:
            st.info("Click Draw file graph when you have a filter (Flask: `src/flask`).")
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
    st.subheader("Browse the tree")
    st.write("Start at the repo root and click folders — no need to know function names.")

    prefix_key = f"browse_prefix_{repository_id}"
    if prefix_key not in st.session_state:
        st.session_state[prefix_key] = ""
    prefix = st.session_state[prefix_key]

    crumbs = [("(root)", "")]
    if prefix:
        parts = prefix.split("/")
        acc = []
        for part in parts:
            acc.append(part)
            crumbs.append((part, "/".join(acc)))
    crumb_cols = st.columns(len(crumbs))
    for i, (label, value) in enumerate(crumbs):
        if crumb_cols[i].button(label, key=f"crumb-{repository_id}-{i}"):
            st.session_state[prefix_key] = value
            st.rerun()

    dirs, files_here = list_repo_dir(repository_id, prefix)
    col_d, col_f = st.columns(2)
    with col_d:
        st.markdown("**Folders**")
        if not dirs:
            st.caption("None")
        for name in dirs:
            child = f"{prefix}/{name}" if prefix else name
            if st.button(f"📁 {name}", key=f"dir-{repository_id}-{child}"):
                st.session_state[prefix_key] = child
                st.rerun()
    with col_f:
        st.markdown("**Files**")
        if not files_here:
            st.caption("None in this folder")
        else:
            pick_file = st.selectbox("File", files_here, key="browse_file")
            row = file_row_by_path(repository_id, pick_file)
            if row:
                fns = (
                    SessionLocal()
                    .query(Function)
                    .filter_by(file_id=row.id)
                    .order_by(Function.start_line)
                    .all()
                )
                st.caption(f"{len(fns)} functions in `{pick_file}`")
                if fns:
                    labels = {
                        f"{fn.qualified_name}  L{fn.start_line}–{fn.end_line}": fn.id
                        for fn in fns
                    }
                    pick = st.selectbox("Function in file", list(labels.keys()), key="browse_fn")
                    render_inspector(labels[pick], repository_id)

    st.divider()
    st.markdown("**Likely entry files** (app.py / main.py / __init__.py)")
    entries = likely_entry_files(repository_id)
    if not entries:
        st.caption("None detected.")
    else:
        for row in entries:
            path = row.path.replace("\\", "/")
            if st.button(path, key=f"entry-{row.id}"):
                parent = "/".join(path.split("/")[:-1])
                st.session_state[prefix_key] = parent
                st.rerun()

    st.divider()
    st.markdown("**Or search if you already have a name**")
    browse_q = st.text_input("Name or path", placeholder="optional", key="browse_search")
    if browse_q:
        browse_pairs = search_functions(
            repository_id, browse_q, total_count=function_count
        )
        if not browse_pairs:
            st.info("No matches.")
        else:
            labels = {loc_label(fn, file_row): fn.id for fn, file_row in browse_pairs}
            pick = st.selectbox("Match", sorted(labels.keys()), key="browse_func")
            render_inspector(labels[pick], repository_id)

