import sys

from app.embeddings.search import semantic_search


def main(query: str, repository_id: int, top_k: int = 5):
    results = semantic_search(query, repository_id=repository_id, top_k=top_k)

    print(f"Top {top_k} matches for '{query}' in repository_id={repository_id}:")
    for func, distance in results:
        print(f"  {func.qualified_name}  (distance: {distance:.4f})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m app.scripts.search <query> <repository_id> [top_k]")
        sys.exit(1)

    query_arg = sys.argv[1]
    repo_id_arg = int(sys.argv[2])
    top_k_arg = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    main(query_arg, repo_id_arg, top_k_arg)