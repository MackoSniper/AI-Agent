import os

import pytest

from functions import security_utils


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(security_utils, "WORKING_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("path", ["file.txt", "sub/file.txt", "sub/../file.txt", "."])
def test_paths_inside_workdir_are_safe(workdir, path):
    assert security_utils.is_safe_path(path)


@pytest.mark.parametrize("path", ["../file.txt", "../../etc/passwd", "/etc/passwd", "sub/../../x"])
def test_paths_outside_workdir_are_blocked(workdir, path):
    assert not security_utils.is_safe_path(path)


def test_sibling_dir_with_same_prefix_is_blocked(workdir):
    # /tmp/work vs /tmp/work_evil: zwykłe startswith() by to przepuściło, commonpath nie
    sibling = f"../{workdir.name}_evil/x.txt"
    assert not security_utils.is_safe_path(sibling)


def test_get_safe_path_returns_absolute_path(workdir):
    assert security_utils.get_safe_path("a/b.txt") == os.path.join(str(workdir), "a", "b.txt")


def test_get_safe_path_raises_outside_workdir(workdir):
    with pytest.raises(PermissionError):
        security_utils.get_safe_path("../secret.txt")
