import ast
from pathlib import Path


def extract_imports(file_path):
    file_path = Path(file_path)
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports = []

    for node in tree.body:  # tree.body is a list of nodes in the file
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "target_module": alias.name,
                    "imported_symbol": None,
                })

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = "." * node.level + node.module
            else:
                module = "." * node.level  # relative import with no name, e.g. "from . import tasks"

            for alias in node.names:
                imports.append({
                    "target_module": module,
                    "imported_symbol": alias.name,
                })

    return imports


"""
reads the top-level import ... and from ... import ... lines that exist in one file,
and turns each one into a structured record (target_module, imported_symbol) instead of leaving it
as raw text
"""