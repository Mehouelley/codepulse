from codepulse.git_data import normalize_path


def test_plain_path_unchanged():
    assert normalize_path("src/app.py") == "src/app.py"


def test_simple_rename_keeps_new_path():
    assert normalize_path("old.py => new.py") == "new.py"


def test_compact_rename_notation():
    assert normalize_path("src/{old => new}/file.py") == "src/new/file.py"
