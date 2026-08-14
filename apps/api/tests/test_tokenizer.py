from app.ingestion.tokenizer import count_tokens, decode, encode


def test_encode_decode_round_trip() -> None:
    text = "Chapter 4 — the one about tokens."

    assert decode(encode(text)) == text
    assert count_tokens(text) == len(encode(text))


def test_special_token_text_is_treated_as_ordinary_text() -> None:
    """Book text can contain anything; encoding must not raise on it."""
    assert count_tokens("the string <|endoftext|> appears in this book") > 0
