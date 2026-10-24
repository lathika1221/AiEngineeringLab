import json
import math
from typing import Any


MAX_ARGUMENT_CHARS = 4096
MAX_AST_NODES = 100
MAX_AST_DEPTH = 40


def calculate(expression: str) -> dict[str, Any]:
    import ast
    import operator

    if not isinstance(expression, str) or len(expression) > 200:
        raise ValueError("Expression must be a string of at most 200 characters.")

    parenthesis_depth = 0
    for character in expression:
        if character == "(":
            parenthesis_depth += 1
            if parenthesis_depth > MAX_AST_DEPTH:
                raise ValueError("Expression nesting limit exceeded.")
        elif character == ")":
            parenthesis_depth -= 1
            if parenthesis_depth < 0:
                raise ValueError("Invalid arithmetic expression.")

    if parenthesis_depth != 0:
        raise ValueError("Invalid arithmetic expression.")

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.BinOp) and type(node.op) in operators:
            left = evaluate(node.left)
            right = evaluate(node.right)

            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponent is too large.")

            value = operators[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            value = operators[type(node.op)](evaluate(node.operand))
        else:
            raise ValueError("Only basic arithmetic expressions are allowed.")

        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Calculation must produce a finite number.")

        if abs(value) > 1e100:
            raise ValueError("Calculation result is too large.")

        return value

    try:
        tree = ast.parse(expression, mode="eval")
        node_count = 0
        stack = [(tree, 1)]

        while stack:
            node, depth = stack.pop()
            node_count += 1

            if node_count > MAX_AST_NODES:
                raise ValueError("Expression complexity limit exceeded.")

            if depth > MAX_AST_DEPTH:
                raise ValueError("Expression nesting limit exceeded.")

            stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))

        result = evaluate(tree.body)
    except (SyntaxError, ZeroDivisionError, OverflowError, RecursionError) as exc:
        raise ValueError("Invalid arithmetic expression.") from exc

    return {"expression": expression, "result": result}


TOOLS = {
    "calculate": {
        "description": "Evaluate a basic arithmetic expression without executing code.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A basic arithmetic expression.",
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        "function": calculate,
    }
}


def get_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for name, tool in TOOLS.items()
    ]


def execute_tool(name: str, arguments: str | dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")

    if isinstance(arguments, str):
        if len(arguments) > MAX_ARGUMENT_CHARS:
            raise ValueError("Tool arguments exceed the size limit.")
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError("Tool arguments must be valid JSON.") from exc

    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")

    if set(arguments) != {"expression"}:
        raise ValueError("Invalid arguments for calculate.")

    result = TOOLS[name]["function"](**arguments)
    json.dumps(result, allow_nan=False)
    return result
