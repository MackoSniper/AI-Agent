from functions.task_manager import add_task, clear_tasks, finish_task, list_tasks


def test_empty_list(tmp_path):
    assert list_tasks(str(tmp_path)) == "Task list is empty."


def test_add_list_and_finish(tmp_path):
    wd = str(tmp_path)

    assert "Task added" in add_task(wd, "Napisz README")
    add_task(wd, "Dodaj testy")
    listing = list_tasks(wd)
    assert "Napisz README" in listing and "Dodaj testy" in listing

    assert "marked as done" in finish_task(wd, 1)


def test_finish_unknown_task(tmp_path):
    assert finish_task(str(tmp_path), 99).startswith("Error: Task ID 99 not found")


def test_clear_tasks(tmp_path):
    wd = str(tmp_path)
    add_task(wd, "cokolwiek")

    assert clear_tasks(wd) == "Task list cleared."
    assert list_tasks(wd) == "Task list is empty."


def test_tasks_persist_between_calls(tmp_path):
    wd = str(tmp_path)
    add_task(wd, "saved to disk")
    assert (tmp_path / "tasks.json").exists()
    assert "saved to disk" in list_tasks(wd)
