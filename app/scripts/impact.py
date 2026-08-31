"""
    Python's standard way of handling command-line flags like --function-id, --direction, --depth — instead of positional 
    sys.argv[1], sys.argv[2], etc.This lets us call things by name in any order, and it auto-generates a --help message and validates input
    e.g. choices=["callers", "callees"] means it'll reject any other value automatically, with a clear error). type=int on --function-id means argparse converts 
    it from the command-line string to a real integer 
"""

#this script is used to find the functions that call or are called by a given function, up to a given depth

import argparse

from app.db.session import SessionLocal
from app.db.models import Function
from app.graph.traversal import get_callers_bfs, get_callees_bfs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--function-id", type=int, required=True)
    parser.add_argument("--direction", choices=["callers", "callees"], required=True)
    parser.add_argument("--depth", type=int, default=3)
    args = parser.parse_args()

    db = SessionLocal()
    target = db.get(Function, args.function_id)
    if target is None:
        print(f"No function found with id {args.function_id}")
        return

    if args.direction == "callers":
        results = get_callers_bfs(args.function_id, depth=args.depth)
        print(f"Functions that call '{target.qualified_name}' (up to {args.depth} hops):")
    else:
        results = get_callees_bfs(args.function_id, depth=args.depth)
        print(f"Functions that '{target.qualified_name}' calls (up to {args.depth} hops):")

    if not results:
        print("  (none found)")
    for fn, hop in sorted(results, key=lambda r: r[1]):
        print(f"  {fn.qualified_name}  (depth {hop})")


if __name__ == "__main__":
    main()