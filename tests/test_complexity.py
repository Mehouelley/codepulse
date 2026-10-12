from codepulse import complexity


def test_empty_file():
    assert complexity.measure(b"") == (0, 1)


def test_counts_decision_points():
    code = b"if a:\n    for b in c:\n        pass\n"
    lines, cx = complexity.measure(code)
    assert lines == 3
    assert cx == 3  # 1 base + "if" + "for"


def test_boolean_operators_count():
    _, cx = complexity.measure(b"x = a && b || c\n")
    assert cx == 3  # 1 base + && + ||


def test_last_line_without_newline_counts():
    lines, _ = complexity.measure(b"a\nb")
    assert lines == 2


def test_binary_is_neutral():
    _, cx = complexity.measure(b"\x00\x01if\nfor\nwhile\x00")
    assert cx == 1  # binary files have no meaningful complexity
