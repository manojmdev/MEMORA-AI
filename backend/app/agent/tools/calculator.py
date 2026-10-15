"""
MEMORA AI — Safe Arithmetic Calculator Tool
Evaluates mathematical expressions using Python's AST parser with zero eval, exec, or shell execution.
Hardened against resource exhaustion, deep nesting, overflow, and non-finite values.
"""
import ast
import math
import operator
import logging
import re
from typing import Any, Union, Dict
from app.agent.models import ToolPermission
from app.agent.tools.base import BaseTool

logger = logging.getLogger(__name__)

MAX_EXPRESSION_LENGTH = 150
MAX_AST_DEPTH = 8
MAX_AST_NODES = 40
MAX_DIGITS_PER_LITERAL = 40
MAX_RESULT_MAGNITUDE = 1e15

SAFE_OPERATORS = {
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

def _validate_ast_limits(node: ast.AST, current_depth: int = 1) -> int:
    """Validate that the AST does not exceed recursion depth or total node complexity limits."""
    if current_depth > MAX_AST_DEPTH:
        raise ValueError(f"Expression exceeds maximum allowed nesting depth of {MAX_AST_DEPTH}.")
    node_count = 1
    for child in ast.iter_child_nodes(node):
        node_count += _validate_ast_limits(child, current_depth + 1)
    if node_count > MAX_AST_NODES:
        raise ValueError(f"Expression exceeds maximum allowed complexity ({MAX_AST_NODES} AST nodes).")
    return node_count

def _eval_ast(node: ast.AST) -> Union[int, float]:
    """Recursively evaluate an AST expression with strict node type allowlisting and resource limits."""
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    elif isinstance(node, ast.Constant):
        # Reject booleans (in Python, bool is an instance of int)
        if isinstance(node.value, bool):
            raise ValueError("Boolean literals are disallowed in arithmetic.")
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

        if isinstance(node.value, float):
            if not math.isfinite(node.value):
                raise ValueError("Non-finite float constants (NaN or Infinity) are disallowed.")
            if abs(node.value) > MAX_RESULT_MAGNITUDE:
                raise ValueError(f"Float literal exceeds maximum allowed magnitude ({MAX_RESULT_MAGNITUDE}).")
        elif isinstance(node.value, int):
            if len(str(abs(node.value))) > MAX_DIGITS_PER_LITERAL:
                raise ValueError(f"Integer literal exceeds maximum allowed size of {MAX_DIGITS_PER_LITERAL} digits.")
            if abs(node.value) > MAX_RESULT_MAGNITUDE:
                raise ValueError(f"Integer literal exceeds maximum allowed magnitude ({MAX_RESULT_MAGNITUDE}).")
        return node.value
    elif isinstance(node, ast.BinOp):
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Disallowed operator: {op_type.__name__}")

        # Power protection against CPU exhaustion and complex outputs
        if op_type is ast.Pow:
            if left < 0 and isinstance(right, float) and not right.is_integer():
                raise ValueError("Fractional powers of negative numbers produce complex results and are disallowed.")
            if abs(right) > 50 or abs(left) > 10000:
                raise ValueError("Exponent or base is excessively large for safe evaluation.")

        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero is undefined.")

        try:
            res = SAFE_OPERATORS[op_type](left, right)
        except OverflowError:
            raise ValueError("Calculation resulted in numerical overflow.")

        if not isinstance(res, (int, float)) or isinstance(res, bool):
            raise ValueError(f"Calculation produced an invalid result type: {type(res).__name__}")

        if not math.isfinite(res):
            raise ValueError("Calculation produced a non-finite result (infinity or NaN).")
        if abs(res) > MAX_RESULT_MAGNITUDE:
            raise ValueError("Calculation result exceeds maximum allowed magnitude (1e15).")
        return res

    elif isinstance(node, ast.UnaryOp):
        operand = _eval_ast(node.operand)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Disallowed unary operator: {op_type.__name__}")
        try:
            res = SAFE_OPERATORS[op_type](operand)
        except OverflowError:
            raise ValueError("Unary calculation resulted in numerical overflow.")

        if not isinstance(res, (int, float)) or isinstance(res, bool):
            raise ValueError(f"Unary calculation produced an invalid result type: {type(res).__name__}")
        if not math.isfinite(res):
            raise ValueError("Unary calculation produced a non-finite result (infinity or NaN).")
        if abs(res) > MAX_RESULT_MAGNITUDE:
            raise ValueError("Unary calculation result exceeds maximum allowed magnitude (1e15).")
        return res
    else:
        raise ValueError(f"Disallowed expression node: {type(node).__name__}")

class CalculatorTool(BaseTool):
    name = "calculator"
    description = (
        "Perform exact mathematical and arithmetic calculations safely. "
        "Accepts an 'expression' string (e.g., '(15 * 4) + 20' or '1024 / 8')."
    )
    permission = ToolPermission.AUTOMATIC

    async def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        """Execute arithmetic calculation securely without eval."""
        expression = (
            kwargs.get("expression")
            or kwargs.get("expr")
            or kwargs.get("calculation")
            or kwargs.get("formula")
            or kwargs.get("query")
            or ""
        )
        if not expression or not isinstance(expression, str):
            raise ValueError("Calculator requires a non-empty string 'expression' argument.")

        clean_expr = expression.strip()
        # Strip common English query wrappers produced by LLMs
        for prefix in ["calculate", "compute", "what is", "eval"]:
            if clean_expr.lower().startswith(prefix):
                clean_expr = clean_expr[len(prefix):].strip()

        # Strip trailing explanation clauses (e.g. 'to find...')
        clean_expr = re.sub(r"\s+to\s+(?:find|calculate|get|determine|estimate).*", "", clean_expr, flags=re.IGNORECASE).strip()

        if len(clean_expr) > MAX_EXPRESSION_LENGTH:
            raise ValueError(f"Expression exceeds maximum allowed length of {MAX_EXPRESSION_LENGTH} characters.")

        try:
            parsed = ast.parse(clean_expr, mode="eval")
            _validate_ast_limits(parsed)
            result = _eval_ast(parsed)
            # Normalize float if integer
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            return {
                "expression": clean_expr,
                "result": result
            }
        except SyntaxError as e:
            raise ValueError(f"Invalid mathematical syntax: {e}")
        except ZeroDivisionError as e:
            raise ValueError("Math error: division by zero.")
        except Exception as e:
            raise ValueError(f"Calculation failed: {str(e)}")
