from mnemosyne.core import embeddings
from mnemosyne.core.beam import _recall_tokens


def test_recall_tokens_preserve_unicode_words():
    tokens = _recall_tokens(
        "Stoßlüften im Bürgeramt: Primärquellen für den Mensa-Plan prüfen"
    )

    assert "stoßlüften" in tokens
    assert "bürgeramt" in tokens
    assert "primärquellen" in tokens
    assert "mensa-plan" in tokens
    assert "sto" not in tokens
    assert "ften" not in tokens
    assert "rgeramt" not in tokens


def test_sentence_transformers_multilingual_dimensions_are_known():
    assert embeddings._get_embedding_dim(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ) == 384
    assert embeddings._get_embedding_dim(
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    ) == 768
