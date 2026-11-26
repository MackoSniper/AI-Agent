import json
import os

def _get_tasks_path(working_directory):
    return os.path.join(working_directory, "tasks.json")

def _load_tasks(working_directory):
    path = _get_tasks_path(working_directory)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return []

def _save_tasks(working_directory, tasks):
    path = _get_tasks_path(working_directory)
    with open(path, 'w') as f:
        json.dump(tasks, f, indent=2)

def add_task(working_directory, description):
    """Adds a new task to the todo list."""
    tasks = _load_tasks(working_directory)
    new_id = len(tasks) + 1
    tasks.append({"id": new_id, "description": description, "status": "pending"})
    _save_tasks(working_directory, tasks)
    return f"Task added: [ID: {new_id}] {description}"

def list_tasks(working_directory):
    """Lists all current tasks and their status."""
    tasks = _load_tasks(working_directory)
    if not tasks:
        return "Task list is empty."
    
    result = "Current Plan:\n"
    for t in tasks:
        icon = "✅" if t["status"] == "done" else "⬜"
        result += f"{icon} {t['id']}. {t['description']} ({t['status']})\n"
    return result

def finish_task(working_directory, task_id):
    """Marks a task as done."""
    tasks = _load_tasks(working_directory)
    found = False
    for t in tasks:
        if t["id"] == int(task_id):
            t["status"] = "done"
            found = True
            break
    
    if found:
        _save_tasks(working_directory, tasks)
        return f"Task {task_id} marked as done."
    return f"Error: Task ID {task_id} not found."

def clear_tasks(working_directory):
    """Clears all tasks."""
    _save_tasks(working_directory, [])
    return "Task list cleared."


# Schemat narzędzia w formacie OpenAI (działa u wszystkich dostawców; working_directory jest wstrzykiwany automatycznie)
schema_add_task = {
    "type": "function",
    "function": {
        "name": "add_task",
        "description": "Adds a new task to the internal plan. Use this at the start of complex goals.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Description of the task to be done."
                }
            },
            "required": [
                "description"
            ]
        }
    }
}

schema_list_tasks = {
    "type": "function",
    "function": {
        "name": "list_tasks",
        "description": "Shows the current status of all tasks.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

schema_finish_task = {
    "type": "function",
    "function": {
        "name": "finish_task",
        "description": "Marks a specific task as completed.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The ID of the task to complete."
                }
            },
            "required": [
                "task_id"
            ]
        }
    }
}

schema_clear_tasks = {
    "type": "function",
    "function": {
        "name": "clear_tasks",
        "description": "Deletes all tasks from the plan. Use before starting a completely new project.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}
