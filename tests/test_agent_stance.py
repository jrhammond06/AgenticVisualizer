from agent import _normalize_stance, _cap_words, _parse_board_reply
from models import Option

OPTIONS = [
    Option(id="park", label="Park Party"),
    Option(id="bowling", label="Bowling"),
    Option(id="pool", label="Pool"),
]


def test_normalize_stance_accepts_exact_forms():
    assert _normalize_stance("WANT") == "want"
    assert _normalize_stance("OK WITH") == "ok_with"
    assert _normalize_stance("WON'T") == "wont"


def test_normalize_stance_tolerates_case_and_punctuation():
    assert _normalize_stance("want") == "want"
    assert _normalize_stance("wont") == "wont"
    assert _normalize_stance("ok with") == "ok_with"
    assert _normalize_stance("Won't") == "wont"  # curly apostrophe


def test_normalize_stance_rejects_unknown_value():
    assert _normalize_stance("MAYBE") is None


def test_cap_words_leaves_short_text_untouched():
    assert _cap_words("no rain risk", 8) == "no rain risk"


def test_cap_words_truncates_long_text():
    text = "one two three four five six seven eight nine ten"
    result = _cap_words(text, 8)
    assert result == "one two three four five six seven eight…"


def test_parse_board_reply_extracts_all_fields():
    reply = (
        "STANCE: WANT\n"
        "OPTION: Bowling\n"
        "REASON: Everyone can play, even non-swimmers\n"
        "FULL: I think Bowling works best because everyone can join in."
    )
    full_text, stance = _parse_board_reply(reply, OPTIONS)
    assert full_text == "I think Bowling works best because everyone can join in."
    assert stance is not None
    assert stance.stance == "want"
    assert stance.option_id == "bowling"
    assert stance.reason == "Everyone can play, even non-swimmers"
    assert stance.full_text == full_text


def test_parse_board_reply_caps_reason_to_eight_words():
    reply = (
        "STANCE: OK WITH\n"
        "OPTION: Pool\n"
        "REASON: this is a very long reason with way too many words in it\n"
        "FULL: Pool is fine with me."
    )
    _, stance = _parse_board_reply(reply, OPTIONS)
    assert stance.reason == "this is a very long reason with way…"


def test_parse_board_reply_returns_none_stance_on_malformed_output():
    reply = "I think we should go bowling because it's fun for everyone."
    full_text, stance = _parse_board_reply(reply, OPTIONS)
    assert stance is None
    assert full_text == reply


def test_parse_board_reply_returns_none_stance_on_unknown_option():
    reply = (
        "STANCE: WANT\n"
        "OPTION: Laser Tag\n"
        "REASON: sounds exciting\n"
        "FULL: Laser tag would be so much fun."
    )
    full_text, stance = _parse_board_reply(reply, OPTIONS)
    assert stance is None
    assert full_text == "Laser tag would be so much fun."


def test_parse_board_reply_matches_option_case_insensitively():
    reply = "STANCE: WANT\nOPTION: bowling\nREASON: fun\nFULL: Bowling please."
    _, stance = _parse_board_reply(reply, OPTIONS)
    assert stance.option_id == "bowling"
