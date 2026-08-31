import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.db.models import File, Function, Embedding
from app.embeddings.text_template import build_embedding_text
from app.embeddings.generate import embed_text


def main(repository_id: int):
    db = SessionLocal()

    # clear old embeddings for this repo before regenerating
    file_ids = [f.id for f in db.query(File).filter_by(repository_id=repository_id).all()]
    function_ids = [f.id for f in db.query(Function).filter(Function.file_id.in_(file_ids)).all()]
    db.query(Embedding).filter(
        Embedding.entity_type == "function",
        Embedding.entity_id.in_(function_ids),
    ).delete(synchronize_session=False)
    db.commit()

    functions = db.query(Function).filter(Function.file_id.in_(file_ids)).all()

    embedded_count = 0
    for func in functions:
        file_row = db.get(File, func.file_id)
        full_path = Path("data/repos") / str(repository_id) / file_row.path
        if not full_path.exists():
            full_path = Path("tests/fixtures/shop") / file_row.path

        text = build_embedding_text(func, full_path)
        vector = embed_text(text)

        db.add(Embedding(
            entity_type="function",
            entity_id=func.id,
            vector=vector,
            model_name="all-MiniLM-L6-v2",
        ))
        embedded_count += 1

    db.commit()
    print(f"Embedded {embedded_count} functions for repository_id={repository_id}")


if __name__ == "__main__":
    main(int(sys.argv[1]))