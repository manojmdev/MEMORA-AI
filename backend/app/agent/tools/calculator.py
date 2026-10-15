"""
MEMORA AI — Safe Arithmetic Calculator Tool
Evaluates mathematical expressions using Python's AST parser with zero eval, exec, or shell execution.
"""
import ast
import operator
import logging
import re
from typing import Any, Union, Dict
from app.agent.models import ToolPermission
from app.agent.tools.base import BaseTool

logger = logging.getLogger(__name__)

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

def _eval_ast(node: ast.AST) -> Union[int, float]:
    """Recursively evaluate an AST expression with strict node type allowlisting."""
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.BinOp):
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Disallowed operator: {op_type.__name__}")

        # Power protection against CPU exhaustion (e.g. 2**10000000)
        if op_type is ast.Pow:
            if abs(right) > 100 or abs(left) > 10000:
                raise ValueError("Exponent or base is excessively large for safe evaluation.")

        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero is undefined.")

        return SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_ast(node.operand)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Disallowed unary operator: {op_type.__name__}")
        return SAFE_OPERATORS[op_type](operand)
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

        if len(clean_expr) > 200:
            raise ValueError("Expression exceeds maximum allowed length of 200 characters.")


        try:
            parsed = ast.parse(clean_expr, mode="eval")
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
