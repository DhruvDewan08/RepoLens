from sentence_transformers import SentenceTransformer

_model = None


def get_model():
    """
    Loads the embedding model once and reuses it — loading it fresh
    for every function would be extremely slow.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed_text(text: str):
    model = get_model()
    vector = model.encode(text) #converts the text into a vector of floats
    return vector.tolist() #converts the vector into a list of floats