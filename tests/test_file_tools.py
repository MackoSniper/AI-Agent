from config import MAX_CHARS
from functions.get_file_content import get_file_content
from functions.get_files_info import get_files_info
from functions.write_file import write_file


def test_get_files_info_lists_files(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()

    result = get_files_info(str(tmp_path), ".")

    assert "- a.txt: file_size=5 bytes, is_dir=False" in result
    assert "- sub:" in result and "is_dir=True" in result


def test_get_files_info_blocks_path_outside_workdir(tmp_path):
    result = get_files_info(str(tmp_path), "../")
    assert result.startswith("Error: Cannot list")


def test_get_files_info_blocks_absolute_path(tmp_path):
    result = get_files_info(str(tmp_path), "/bin")
    assert result.startswith("Error: Cannot list")


def test_get_files_info_rejects_file_as_directory(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert "is not a directory" in get_files_info(str(tmp_path), "a.txt")


def test_get_file_content_reads_file(tmp_path):
    (tmp_path / "notes.txt").write_text("zażółć gęślą jaźń", encoding="utf-8")
    assert get_file_content(str(tmp_path), "notes.txt") == "zażółć gęślą jaźń"


def test_get_file_content_truncates_long_files(tmp_path):
    (tmp_path / "big.txt").write_text("x" * (MAX_CHARS + 50))

    result = get_file_content(str(tmp_path), "big.txt")

    assert result.startswith("x" * MAX_CHARS)
    assert f"truncated at {MAX_CHARS} characters" in result


def test_get_file_content_blocks_path_traversal(tmp_path):
    result = get_file_content(str(tmp_path), "../../etc/passwd")
    assert result.startswith("Error: Cannot read")


def test_get_file_content_missing_file(tmp_path):
    assert "File not found" in get_file_content(str(tmp_path), "nope.txt")


def test_write_file_creates_nested_dirs(tmp_path):
    result = write_file(str(tmp_path), "out/deep/hello.py", "print('hi')")

    assert result.startswith("Successfully wrote")
    assert (tmp_path / "out" / "deep" / "hello.py").read_text() == "print('hi')"


def test_write_file_blocks_path_outside_workdir(tmp_path):
    work = tmp_path / "work"
    work.mkdir()

    result = write_file(str(work), "../escape.txt", "nope")

    assert result.startswith("Error: Cannot write")
    assert not (tmp_path / "escape.txt").exists()


def test_write_file_rejects_directory_target(tmp_path):
    (tmp_path / "folder").mkdir()
    assert "is a directory" in write_file(str(tmp_path), "folder", "x")
