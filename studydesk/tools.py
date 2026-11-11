"""Allowlisted actions. Model output is always data, never executable code."""
import ast
import math
import operator
import os
import re
from pathlib import Path


class AgentError(Exception):
    """An error that is safe to display to the user."""


TOOL_ARGS = {
    "note.save": {"name": str, "content": str},
    "note.read": {"name": str},
    "note.list": {},
    "note.delete": {"name": str},
    "task.add": {"title": str},
    "task.list": {},
    "task.complete": {"task_id": int},
    "task.delete": {"task_id": int},
    "calc.evaluate": {"expression": str},
}


def validate_plan(value):
    if not isinstance(value, dict) or set(value) != {"summary", "actions"}:
        raise AgentError("The planner returned an invalid plan structure.")
    if not isinstance(value["summary"], str) or not 1 <= len(value["summary"]) <= 1000:
        raise AgentError("The plan needs a short summary.")
    actions = value["actions"]
    if not isinstance(actions, list) or len(actions) > 8:
        raise AgentError("A plan can contain at most eight actions.")
    clean = []
    for action in actions:
        if not isinstance(action, dict) or set(action) != {"tool", "arguments"}:
            raise AgentError("Invalid action structure.")
        tool, args = action["tool"], action["arguments"]
        if not isinstance(tool, str) or tool not in TOOL_ARGS or not isinstance(args, dict):
            raise AgentError("The plan contains an unsupported action.")
        # Structured Outputs uses nullable fields for the fixed argument shape.
        if set(args) - {"name", "content", "title", "task_id", "expression"}:
            raise AgentError("Unexpected action arguments.")
        args = {k: v for k, v in args.items() if v is not None}
        expected = TOOL_ARGS[tool]
        if set(args) != set(expected):
            raise AgentError(f"Incorrect arguments for {tool}.")
        for key, expected_type in expected.items():
            if type(args[key]) is not expected_type:
                raise AgentError(f"Invalid {key} for {tool}.")
        if "name" in args:
            validate_name(args["name"])
        if "content" in args and len(args["content"]) > 20000:
            raise AgentError("Notes are limited to 20,000 characters.")
        if "title" in args and not 1 <= len(args["title"].strip()) <= 200:
            raise AgentError("Task titles must be between 1 and 200 characters.")
        if "task_id" in args and not 1 <= args["task_id"] <= 2147483647:
            raise AgentError("Task IDs must be positive integers.")
        if "expression" in args:
            calculate(args["expression"])  # reject unsafe syntax before preview
        clean.append({"tool": tool, "arguments": args})
    return {"summary": value["summary"], "actions": clean}


def validate_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.(?:txt|md)", name):
        raise AgentError("Use a simple .txt or .md filename, such as exam.md (no folders).")
    if name.rsplit(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise AgentError("This filename is reserved by the operating system.")


def note_path(root, name):
    validate_name(name)
    root = Path(root).resolve()
    path = root / name
    if path.is_symlink() or path.resolve().parent != root:
        raise AgentError("This file is outside the note workspace.")
    return path


def calculate(expression):
    """Evaluate bounded arithmetic without eval, function calls, or attributes."""
    if not isinstance(expression, str) or not 1 <= len(expression) <= 200:
        raise AgentError("Use an arithmetic expression of at most 200 characters.")
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                  ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
                  ast.Mod: operator.mod, ast.Pow: operator.pow}
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 60:
            raise AgentError("The expression is too complex.")

        def visit(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                result = node.value
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            elif isinstance(node, ast.BinOp) and type(node.op) in operations:
                left, right = visit(node.left), visit(node.right)
                if isinstance(node.op, ast.Pow) and abs(right) > 12:
                    raise AgentError("Exponents must be between -12 and 12.")
                result = operations[type(node.op)](left, right)
            else:
                raise AgentError("Only numbers, parentheses, and arithmetic operators are allowed.")
            if type(result) not in (int, float) or not math.isfinite(result) or abs(result) > 1e15:
                raise AgentError("The calculation exceeds the supported numeric range.")
            return result

        return visit(tree.body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, RecursionError) as exc:
        raise AgentError("Invalid calculation, division by zero, or numeric overflow.") from exc


def risks(actions, root):
    """Track writes within the plan too, so two saves cannot bypass overwrite review."""
    existing = {os.path.normcase(p.name) for p in Path(root).iterdir()}
    warnings = []
    for action in actions:
        tool, args = action["tool"], action["arguments"]
        if tool == "note.save":
            name = os.path.normcase(args["name"])
            if name in existing:
                warnings.append(f"Overwrite note {args['name']}")
            existing.add(name)
        elif tool == "note.delete":
            warnings.append(f"Delete note {args['name']}")
            existing.discard(os.path.normcase(args["name"]))
        elif tool == "task.delete":
            warnings.append(f"Delete task #{args['task_id']}")
    return warnings


def execute_action(action, root, conn):
    tool, args = action["tool"], action["arguments"]
    if tool == "calc.evaluate":
        return {"expression": args["expression"], "value": calculate(args["expression"])}
    if tool == "note.list":
        return {"notes": sorted(p.name for p in Path(root).iterdir()
                                if p.is_file() and not p.is_symlink())}
    if tool.startswith("note."):
        path = note_path(root, args["name"])
        if tool == "note.save":
            if not path.exists() and len(list(Path(root).iterdir())) >= 100:
                raise AgentError("The workspace limit is 100 notes.")
            path.write_text(args["content"], encoding="utf-8")
            return {"saved": path.name, "characters": len(args["content"])}
        if not path.is_file():
            raise AgentError(f"Note {path.name} does not exist.")
        if tool == "note.read":
            return {"name": path.name, "content": path.read_text(encoding="utf-8")}
        path.unlink()
        return {"deleted": path.name}
    if tool == "task.add":
        if conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] >= 500:
            raise AgentError("The workspace limit is 500 tasks.")
        cursor = conn.execute("INSERT INTO tasks(title) VALUES (?)", (args["title"].strip(),))
        return {"id": cursor.lastrowid, "title": args["title"].strip(), "done": False}
    if tool == "task.list":
        return {"tasks": [dict(row) for row in conn.execute("SELECT * FROM tasks ORDER BY id DESC")]}
    task_id = args["task_id"]
    if not conn.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone():
        raise AgentError(f"Task #{task_id} does not exist.")
    if tool == "task.complete":
        conn.execute("UPDATE tasks SET done=1 WHERE id=?", (task_id,))
        return {"completed": task_id}
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    return {"deleted": task_id}
