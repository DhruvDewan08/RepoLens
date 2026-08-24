import os
import shutil
import stat
import subprocess
from pathlib import Path


def _rmtree_force(path: Path) -> None:
    """Delete a tree even when Git marks pack files read-only (Windows)."""

    def onerror(func, target, _exc_info):
        os.chmod(target, stat.S_IWRITE) #change the file permissions to writable and then calss the function again, which retries the deletion.
        func(target)

    shutil.rmtree(path, onerror=onerror) #accepts an onerror callback — when deletion fails on some file, instead of just crashing, it will try to change the file permissions to writable and then delete it.


def clone_repo(url: str, dest, branch: str | None = None) -> str:
    """
    Shallow-clones the given GitHub URL into `dest`.
    Returns the commit SHA of the cloned HEAD.
    """
    dest = Path(dest)

    if dest.exists():
        _rmtree_force(dest)

    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [url, str(dest)]

    subprocess.run(cmd, check=True)
    result = subprocess.run(
        ["git","-C",str(dest),"rev-parse","HEAD"],  # Get the commit SHA of the cloned HEAD, c str(dest) to run this command as in you are in the folder 
        capture_output=True, #print the output as a python string instead of terminal output
        text=True,
        check=True
    )
    return result.stdout.strip()
    
