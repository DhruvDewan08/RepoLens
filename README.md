# RepoLens

RepoLens indexes a Python repository into a **call graph**, an **import graph**, and **function-level embeddings**. It answers questions about code from program structure, not from file chunks.

### What it can do

-  Ask questions about a repository using function-level semantic retrieval
-  Explore import and function-call relationships
-  Run caller/callee impact analysis with BFS
-  Generate grounded answers from retrieved functions + graph context

![Architecture](docs/screenshots/architecture.png)

---

## Demo

Capture these from a running session against `tests/fixtures/shop`:

| File | Shows |
|------|-------|
| `docs/screenshots/chat.png` | Chat — question, answer, grounding context |
| `docs/screenshots/impact.png` | Impact analysis — graph and source pane |
| `docs/screenshots/folders.png` | File graph or function browser |

![Chat](docs/screenshots/chat.png)
![Impact analysis](docs/screenshots/impact.png)
![Folder / function explorer](docs/screenshots/folders.png)

---

## How it works

Typical repo-QA tools work like this:

```text
files → split into chunks → embed → LLM
```

The model sees text. It doesn't know who calls whom.

RepoLens builds structure first:

```text
GitHub URL or local folder
  → clone / walk *.py
  → AST: functions, imports, calls
  → resolve call edges to function IDs
  → embed each function (path, name, docstring, snippet)
  → route intent: semantic | impact | both
  → LLM answers from graph + retrieved functions
```

Questions like *what breaks if I change `checkout`?* are answered with a BFS over real AST-derived edges, not a similarity search over text chunks.

---

## Example: question → retrieval → answer

**Question:** *What breaks if I change `get_total_value`?*

Against `tests/fixtures/shop`:

1. **Router** classifies this as an **impact** query (`break` / `breaks` in `app/query/router.py`).
2. **Semantic search** finds `get_total_value` (and nearby functions) via pgvector.
3. **Graph traversal** BFS-walks **callers** (and callees) of the best match: `checkout` → `add_and_checkout`.
4. **Context packet** is built: function snippets + a neighborhood summary (`app/query/context_builder.py`).
5. **LLM** explains the blast radius from that packet only — not the whole repo.

Resolved call graph for the fixture:

```text
add_and_checkout
    ├── checkout ──► get_total_value
    └── add_product ──► Product (constructor; typically unresolved)
```

`checkout` also calls `math.ceil` (unresolved). Changing `get_total_value` therefore affects `checkout` and `add_and_checkout`.

```bash
python -m app.scripts.search "checkout" 1
python -m app.scripts.impact --function-id <id> --direction callers --depth 3
python -m app.scripts.ask "What breaks if I change get_total_value?" 1
```

---

## Architecture

| Layer | Choice |
|--------|--------|
| Language | Python 3.11 |
| UI | Streamlit (`streamlit_app.py`) |
| API | FastAPI (`app/api/main.py`) |
| DB | PostgreSQL + **pgvector** (`pgvector/pgvector:pg16`) |
| ORM | SQLAlchemy |
| Parse | stdlib `ast` |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` |
| LLM | Groq, OpenAI-compatible, or local Ollama |
| Graphs | Graphviz (system binary, not only the pip package) |

| Step | Module | Writes |
|------|--------|--------|
| Ingest | `app.scripts.ingest` / `ingest_local` | `Repository`, `File` |
| Parse | `app.scripts.parse` | `Function`, `Import`, raw `FunctionCall` |
| Resolve | `app.graph.resolve_calls` | `callee_function_id` (same-file + `from x import y`) |
| Embed | `app.scripts.embed` | `Embedding` vectors |
| Query | `search` / `impact` / `ask` | reads only |

---

## Technical design

- **Six tables:** `Repository` → `File` → `Function`; `Import`; `FunctionCall`; `Embedding` (`Vector(384)`).
- **Structure and meaning, kept separate:** pgvector cosine search over function embeddings, plus SQL call edges — merged at query time.
- **CLI-first:** Streamlit and FastAPI call the same scripts (`python -m app.scripts.*`).
- **Large repos:** Streamlit does not dump every function as a Graphviz node or a button. File graph and function browse are folder- and search-scoped.

### Key engineering decisions

#### AST over text chunking

Functions, imports, and calls are extracted structurally rather than treating source files as arbitrary text.

#### SQL edges over a dedicated graph database

V1 uses PostgreSQL for both relational graph edges and pgvector, avoiding an additional graph database dependency.

#### Graph + semantic retrieval

Embeddings answer conceptual questions; graph traversal answers structural questions such as callers and impact.

#### Best-effort call resolution

Static Python analysis cannot reliably resolve every dynamic call. RepoLens stores unresolved callees (`callee_function_id` null, `callee_name` kept) instead of inventing edges. Same-file and `from x import y` calls resolve; `obj.method()`, constructors, and stdlib names such as `math.ceil` stay unresolved. Impact walks **resolved** edges; unresolved names can still appear in LLM context.

---

## Quick start

### 1. Database

```bash
docker compose up -d db
```

`postgresql://postgres:postgres@localhost:5432/repolens`

Compose mounts `docker/init/01-vector.sql` (`CREATE EXTENSION IF NOT EXISTS vector`) on **first volume init**. `check_db` / `reset_db` run the same statement so an existing volume still gets the extension.

### 2. Python

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Install [Graphviz](https://graphviz.org/download/) for Streamlit graphs.

### 3. Environment

Create `.env` (gitignored):

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/repolens
```

LLM selection in `app/query/llm_client.py`:

1. If `GROQ_API_KEY` is set → Groq OpenAI-compatible API. Default model: `llama-3.1-8b-instant` (override with `LLM_MODEL`).
2. Else if `OPENAI_API_KEY` is set → OpenAI (or `OPENAI_BASE_URL`). Default model: `gpt-4o-mini`.
3. Else → local Ollama. Default model: `llama3.2`.

Optional:

```env
GROQ_API_KEY=...
# OPENAI_API_KEY=...
# OPENAI_BASE_URL=...
# LLM_MODEL=...
```

### 4. Schema

```bash
python -m app.scripts.check_db
```

Enables `vector` if needed, then creates the six tables.

### 5. Index the fixture

```bash
python -m app.scripts.ingest_local tests/fixtures/shop shop-fixture
python -m app.scripts.parse 1
python -m app.graph.resolve_calls 1
python -m app.scripts.embed 1
```

Use the printed `repository_id` if it is not `1`.

### 6. UI

```bash
streamlit run streamlit_app.py
```

Tabs: **Chat** · **Impact** · **File graph** · **Functions**. The sidebar can clone a GitHub URL and run the same pipeline.

### 7. Optional API

```bash
uvicorn app.api.main:app --reload
```

| Method | Path |
|--------|------|
| `GET` | `/health` |
| `POST` | `/repositories` |
| `GET` | `/repositories/{id}` |
| `POST` | `/repositories/{id}/ask` |
| `GET` | `/functions/{id}/impact` |

OpenAPI: `http://127.0.0.1:8000/docs`

---

## Project structure

```text
app/
  ingestion/    clone, walk
  parsing/      functions, imports, calls
  graph/        resolve, BFS impact, folder/file import map
  embeddings/   template, MiniLM, pgvector search
  query/        router, context packet, LLM, source inspector
  api/          FastAPI
  scripts/      CLI
  db/           models + session
docker/init/    CREATE EXTENSION vector (first Postgres boot)
tests/fixtures/shop/
streamlit_app.py
docker-compose.yaml
```

---

## Limitations & V1 scope

- No hosted demo — run locally (Docker + Python + Groq, OpenAI, or Ollama).
- Call resolution is same-file and import-based only; no interprocedural or type-aware analysis.
- API keys live in `.env`, never committed. `llm_client.py` only reads `os.getenv`.
