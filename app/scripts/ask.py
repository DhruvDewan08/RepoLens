import sys

from app.query.context_builder import build_context
from app.query.llm_client import ask_llm


def main(question: str, repository_id: int):
    context = build_context(question, repository_id=repository_id)
    print(f"[intent: {context['intent']}]")

    answer = ask_llm(question, context)
    print("\nAnswer:\n")
    print(answer)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python -m app.scripts.ask "<question>" <repository_id>')
        sys.exit(1)

    question_arg = sys.argv[1]
    repo_id_arg = int(sys.argv[2])
    main(question_arg, repo_id_arg)