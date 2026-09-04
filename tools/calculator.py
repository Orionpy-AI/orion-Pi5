# calculator.py
"""Safe arithmetic evaluator — no eval(), no arbitrary code execution."""
import ast
import operator

_ALLOWED_OPERATORS = {
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


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numeric constants are allowed")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Operator {op_type.__name__} not allowed")
        return _ALLOWED_OPERATORS[op_type](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Operator {op_type.__name__} not allowed")
        return _ALLOWED_OPERATORS[op_type](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def calculator(expression: str) -> str:
    """Safely evaluate a basic arithmetic expression (+ - * / // % ** and parens)."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Calculator error: could not evaluate '{expression}' ({e})"
