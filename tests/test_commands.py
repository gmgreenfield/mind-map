from mindmap.commands import Command, CommandError, parse, unescape


def test_plain_text_is_not_a_command():
    assert parse("hello there") is None
    assert parse("") is None


def test_branch_with_topic():
    assert parse("/branch idea describing this project") == Command(
        "branch", "idea describing this project"
    )
    assert parse("  /Branch   spaced topic  ") == Command("branch", "spaced topic")


def test_branch_without_topic_is_error():
    assert isinstance(parse("/branch"), CommandError)
    assert isinstance(parse("/branch   "), CommandError)


def test_parent_and_map():
    assert parse("/parent") == Command("parent")
    assert parse("/map") == Command("map")


def test_unknown_command():
    err = parse("/frobnicate x")
    assert isinstance(err, CommandError) and "/frobnicate" in err.message


def test_double_slash_escapes():
    assert parse("//branch not a command") is None
    assert unescape("//branch not a command") == "/branch not a command"
    assert unescape("normal") == "normal"
