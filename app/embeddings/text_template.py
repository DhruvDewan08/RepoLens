from pathlib import Path


def build_embedding_text(function_row, file_path, source_lines=30):
    """
    Builds the text to embed for a single function, combining
    metadata (path, name, docstring) with a snippet of the body.
    """
    full_path = Path(file_path)
    all_lines = full_path.read_text(encoding="utf-8").splitlines()

    start = function_row.start_line - 1  # AST line numbers are 1-indexed, list indices are 0-indexed
    end = min(function_row.end_line, start + source_lines)
    snippet = "\n".join(all_lines[start:end])

    docstring = function_row.docstring or ""

    return (
        f"path: {file_path}\n"
        f"name: {function_row.qualified_name}\n"
        f"docstring: {docstring}\n" 
        f"---\n"
        f"{snippet}"
    )