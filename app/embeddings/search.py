from app.db.session import SessionLocal
from app.db.models import Embedding, Function
from app.embeddings.generate import embed_text


def semantic_search(query: str, repository_id: int, top_k: int = 5):
    """
    Embeds the query text and finds the top_k most similar
    function embeddings within the given repository.
    """
    db = SessionLocal()
    query_vector = embed_text(query)

    function_ids_in_repo = [
        f.id for f in
        db.query(Function.id)
        .join(Function.file)
        .filter_by(repository_id=repository_id)
        .all()
    ]

    results = (
        db.query(Embedding, Embedding.vector.cosine_distance(query_vector).label("distance"))
        .filter(
            Embedding.entity_type == "function",
            Embedding.entity_id.in_(function_ids_in_repo),
        )
        .order_by("distance")
        .limit(top_k)
        .all()
    )

    output = []
    for embedding_row, distance in results:
        func = db.get(Function, embedding_row.entity_id)
        output.append((func, distance))
    return output