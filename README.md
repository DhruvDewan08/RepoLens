# RepoLens

**Program-aware code intelligence** — not “chat over file chunks.”

RepoLens indexes a Python repository into a **call graph**, an **import graph**, and **function-level embeddings**. Questions like *what breaks if I change `checkout`?* are answered with a **BFS over real AST-derived edges**, plus an LLM that only sees a curated context packet.

This is a portfolio project for **backend + static analysis + retrieval**. There is no hosted demo: clone, run locally, and walk the UI. That is the interview demo.

![Architecture](docs/screenshots/architecture.svg)

---

## Why this exists

Typical repo-QA:

```text
files → split into chunks → embed → LLM
```

The model sees text. It does not know who calls whom.

RepoLens:

```text
GitHub URL or local folder
  → clone / walk *.py
  → AST: functions, imports, calls
  → resolve call edges to function IDs
  → embed each function (path, name, docstring, snippet)
  → route intent: semantic | impact | both
  → LLM answers from graph + retrieved functions
```

---

## What an interviewer should notice

- **Six tables:** `Repository` → `File` → `Function`; `Import`; `FunctionCall`; `Embedding` (`Vector(384)`).
- **Structure, not only meaning:** pgvector cosine search *and* SQL call edges.
- **CLI first:** the same scripts power Streamlit and FastAPI (`python -m app.scripts.*`).
- **Honest V1 limits:** `math.ceil`, constructors, and most `obj.method()` stay unresolved. Impact uses **resolved** edges; unresolved names still go into LLM context.
- **UI built for large repos:** Flask was ingested as a *sample codebase*, not as the app framework. The UI never dumps every function as a button (that froze Graphviz).

---

## Screenshots (add these before you share the repo)

The architecture diagram above is in the repo. **UI shots must be real captures** of your Streamlit session — interviewers will run the app.

1. Start Postgres and the UI (commands below).
2. Index `tests/fixtures/shop` (the golden demo).
3. Windows: `Win + Shift + S` → save as:

| Save as | What to capture |
|---------|-----------------|
| `docs/screenshots/chat.png` | **Chat** — question + answer + grounding expander |
| `docs/screenshots/impact.png` | **Impact** — graph **and** source pane (`path:line` + code) |
| `docs/screenshots/folders.png` | **File graph** (folder map) **or** **Functions** (tree → file → snippet) |

Then they render here:

![Chat](docs/screenshots/chat.png)

![Impact analysis](docs/screenshots/impact.png)

![Folder / function explorer](docs/screenshots/folders.png)

---

## Stack

| Layer | Choice |
|--------|--------|
| Language | Python 3.11 |
| UI | Streamlit (`streamlit_app.py`) |
| API | FastAPI (`app/api/main.py`) — thin; CLI is the source of truth |
| DB | PostgreSQL + **pgvector** (Docker) |
| ORM | SQLAlchemy |
| Parse | stdlib `ast` |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` |
| LLM | `GROQ_API_KEY` / `OPENAI_API_KEY`, else local **Ollama** |
| Graphs | Graphviz (install the **system** binary, not only the pip package) |

---

## Golden fixture (shop)

`tests/fixtures/shop/` is the graph you can explain on a whiteboard:

```text
add_and_checkout
    ├── checkout ──► get_total_value
    └── add_product ──► Product (constructor; often unresolved in V1)
```

`checkout` also calls `math.ceil` (stdlib — **unresolved**, by design).

After ingest + parse + resolve + embed:

```bash
python -m app.scripts.search "checkout" 1
python -m app.scripts.impact --function-id <id> --direction callers --depth 3
python -m app.scripts.ask "What breaks if I change get_total_value?" 1
```

---

## Quick start

### 1. Database

```bash
docker compose up -d db
```

`postgresql://postgres:postgres@localhost:5432/repolens`

### 2. Python

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Install [Graphviz](https://graphviz.org/download/) for the Streamlit graphs.

### 3. Secrets (never commit)

Create `.env`:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/repolens
GROQ_API_KEY=gsk_...
```

If `GROQ_API_KEY` is unset, the client falls back to Ollama.

### 4. Schema

```bash
python -m app.scripts.check_db
```

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

Tabs: **Chat** · **Impact** · **File graph** · **Functions**. Sidebar can clone a GitHub URL and run the same pipeline.

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

## Pipeline

```mermaid
flowchart LR
  A[GitHub / local] --> B[Ingest]
  B --> C[AST parse]
  C --> D[Resolve calls]
  D --> E[Embed functions]
  E --> F[Router]
  F --> G[LLM]
  G --> H[Streamlit / FastAPI]
```

| Step | Module | Writes |
|------|--------|--------|
| Ingest | `app.scripts.ingest` / `ingest_local` | `Repository`, `File` |
| Parse | `app.scripts.parse` | `Function`, `Import`, raw `FunctionCall` |
| Resolve | `app.graph.resolve_calls` | `callee_function_id` (same-file + `from x import y`) |
| Embed | `app.scripts.embed` | `Embedding` vectors |
| Query | `search` / `impact` / `ask` | reads only |

---

## Layout

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
tests/fixtures/shop/
streamlit_app.py
docker-compose.yaml
```

---

## What this is not

- Not a hosted Render/Railway app (keys, GPU RAM, and Ollama do not fit a free dyno well).
- Not production call-resolution (no interprocedural / type inference).
- Keys live in `.env` only (`llm_client.py` uses `os.getenv`). Do not paste them into GitHub.

---

## Resume one-liner

*Built a program-aware code intelligence tool: AST → call/import graph in Postgres + pgvector, hybrid retrieval, Streamlit + FastAPI, Groq/Ollama.*
