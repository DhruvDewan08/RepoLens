import hashlib
from pathlib import Path

IGNORE_DIRS ={".git",".pytest_cache","__pycache__","venv",".venv","node_modules"}

def walk_python_files(root):
    """
    Walks `root` recursively, yielding metadata for every .py file found.
    Skips common non-source directories.
    """

    root = Path(root)

    for path in root.rglob("*.py"): #recursive glob search for all the .py files in the root directory in depth
        if any(part in IGNORE_DIRS for part in path.parts): #breaks path into parts like data/repo is broken into "data", "repo" and checks if any of the parts are in the IGNORE_DIRS
            continue #if any of the parts are in the IGNORE_DIRS, skip the file
        content = path.read_bytes() #reads the raw bytes of the file as hashlib needs bytes

        yield{
            "path":path.relative_to(root).as_posix(), #converts the path to a string and removes the root directory, and uses the posix format for the path so the DB looks same on every OS
            "size_bytes":len(content),
            "checksum":hashlib.sha256(content).hexdigest(), #generates a hash of the file content , for the File.checksum in the database
        }