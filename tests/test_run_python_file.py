from functions.run_python_file import run_python_file


def test_runs_script_and_passes_args(tmp_path):
    (tmp_path / "echo.py").write_text("import sys\nprint(' '.join(sys.argv[1:]))")

    result = run_python_file(str(tmp_path), "echo.py", ["3", "+", "5"])

    assert "STDOUT:\n3 + 5" in result


def test_reports_exit_code_and_stderr(tmp_path):
    (tmp_path / "fail.py").write_text("import sys\nsys.stderr.write('boom')\nsys.exit(2)")

    result = run_python_file(str(tmp_path), "fail.py")

    assert "Exit Code: 2" in result
    assert "STDERR:\nboom" in result


def test_script_without_output(tmp_path):
    (tmp_path / "quiet.py").write_text("x = 1")
    assert "produced no output" in run_python_file(str(tmp_path), "quiet.py")


def test_blocks_script_outside_workdir(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (tmp_path / "outside.py").write_text("print('should not run')")

    result = run_python_file(str(work), "../outside.py")

    assert result.startswith("Error: Cannot execute")


def test_missing_script(tmp_path):
    assert "does not exist" in run_python_file(str(tmp_path), "nope.py")
