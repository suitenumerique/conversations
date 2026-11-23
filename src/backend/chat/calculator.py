"""Evaluate arithmetic expressions written by the model.

LLMs make arithmetic mistakes with confidence, so the model writes the expression
and this module computes it. The expression is parsed with `ast` and only a
whitelist of nodes is evaluated: numbers, + - * / // % **, unary signs and a few
functions. Nothing is passed to `eval`, so no name, attribute or call outside the
whitelist can be reached.

Arithmetic is done in `Decimal` (no binary float noise on amounts) with a bounded
precision and exponent range, so huge powers overflow with an error instead of
exhausting memory. Each calculation runs in its own decimal context: when a step
had to round, the result is displayed with fewer digits than it was computed with,
like a hand calculator, so 1 / 3 * 3 shows 1, not 0.999...; exact results are
displayed in full.
`round` rounds half up, like people do, not half to even.

Error messages never quote the expression: they are logged on retry, and the
expression is model-written text that can carry user data.
"""

import ast
import decimal
import operator
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

MAX_EXPRESSION_LENGTH = 500
MAX_ROUND_DIGITS = 20
COMPUTE_PRECISION = 34
DISPLAY_PRECISION = 28

_CONTEXT = decimal.Context(
    prec=COMPUTE_PRECISION,
    rounding=ROUND_HALF_UP,
    Emax=999_999,
    Emin=-999_999,
    traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow],
)

_FORMAT_HINT = (
    "Use '.' as decimal separator, no thousands separator (e.g. 1234.56), "
    "and write a percentage as a division (e.g. 15 / 100 * 240)."
)


class CalculationError(Exception):
    """The expression cannot be computed. The message tells the model how to fix it."""


def _round(value: Decimal, digits: Decimal = Decimal(0)) -> Decimal:
    """Round half up to `digits` decimals (negative digits round to tens, hundreds...)."""
    if digits != digits.to_integral_value() or abs(digits) > MAX_ROUND_DIGITS:
        raise CalculationError(
            f"round() digits must be an integer between -{MAX_ROUND_DIGITS} and {MAX_ROUND_DIGITS}."
        )
    try:
        return value.quantize(Decimal(1).scaleb(-int(digits)))
    except decimal.InvalidOperation as exc:
        raise CalculationError(
            f"round() result would have more than {COMPUTE_PRECISION} significant digits: "
            "use fewer decimals."
        ) from exc


def _floor_divide(a: Decimal, b: Decimal) -> Decimal:
    """Floor division like Python's // (Decimal's own truncates toward zero)."""
    return (a / b).to_integral_value(rounding=ROUND_FLOOR)


def _modulo(a: Decimal, b: Decimal) -> Decimal:
    """Modulo with the sign of the divisor, like Python's % (Decimal's follows the dividend)."""
    return a - b * _floor_divide(a, b)


def _sqrt(value: Decimal) -> Decimal:
    if value < 0:
        raise CalculationError("sqrt() of a negative number is not defined.")
    return value.sqrt()


# name -> (function, minimum arguments, maximum arguments or None)
_FUNCTIONS = {
    "round": (_round, 1, 2),
    "abs": (abs, 1, 1),
    "sqrt": (_sqrt, 1, 1),
    "min": (lambda *values: min(values), 1, None),
    "max": (lambda *values: max(values), 1, None),
    "sum": (lambda *values: sum(values, Decimal(0)), 1, None),
}

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: _floor_divide,
    ast.Mod: _modulo,
    ast.Pow: operator.pow,
}


def _arguments(node: ast.Call) -> list[ast.expr]:
    """Function arguments; a single list or tuple argument is spread (sum([1, 2]))."""
    if node.keywords:
        raise CalculationError("Keyword arguments are not supported.")
    if len(node.args) == 1 and isinstance(node.args[0], (ast.List, ast.Tuple)):
        return list(node.args[0].elts)
    return list(node.args)


def _evaluate(node: ast.AST, source: str) -> Decimal:  # pylint: disable=too-many-return-statements
    """Evaluate one whitelisted node of `source` in the current decimal context."""
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, source)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalculationError("Only numbers are allowed.")
        # A float literal is read from its source text: the parsed float has already
        # lost digits past ~17 and turned 1e400 into inf. Unary + applies the context
        # so an out-of-range literal raises Overflow like any other result.
        if isinstance(node.value, float):
            return +Decimal(ast.get_source_segment(source, node))
        return +Decimal(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand, source)
        return -value if isinstance(node.op, ast.USub) else +value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        return _BINARY_OPERATORS[type(node.op)](
            _evaluate(node.left, source), _evaluate(node.right, source)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id not in _FUNCTIONS:
            raise CalculationError(f"Unknown function. Available: {', '.join(_FUNCTIONS)}.")
        function, minimum, maximum = _FUNCTIONS[node.func.id]
        arguments = _arguments(node)
        if len(arguments) < minimum or (maximum is not None and len(arguments) > maximum):
            raise CalculationError(f"Wrong number of arguments for {node.func.id}().")
        return function(*(_evaluate(argument, source) for argument in arguments))
    if isinstance(node, ast.Tuple):
        raise CalculationError(f"Unexpected comma. {_FORMAT_HINT}")
    # The node type only, never its source: see the module docstring.
    raise CalculationError(f"Unsupported syntax ({type(node).__name__}).")


def _format(value: Decimal, inexact: bool) -> str:
    """Render a result without exponent unless very large or small.

    An inexact result is cut to DISPLAY_PRECISION digits, which absorbs the
    rounding error of intermediate steps (0.999...9 becomes 1).
    """
    context = _CONTEXT.copy()
    if inexact:
        context.prec = DISPLAY_PRECISION
    value = context.plus(value).normalize(context=context)
    if value.is_zero():
        return "0"
    if -30 <= value.adjusted() <= 30:
        return format(value, "f")
    return format(value, "e")


def calculate(expression: str) -> tuple[str, str]:
    """Compute an arithmetic expression; return it as written and its formatted result.

    The expression is echoed as written, not re-rendered from the tree: `ast.unparse`
    would print float literals through the float (1e400 becomes 1e309).

    Raises:
        CalculationError: invalid syntax, unsupported construct, division by zero,
            or a result outside the supported range.
    """
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculationError(
            f"Expression too long (over {MAX_EXPRESSION_LENGTH} characters): split it."
        )
    expression = expression.strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculationError(f"Invalid expression. {_FORMAT_HINT}") from exc
    except (RecursionError, MemoryError) as exc:
        raise CalculationError("Expression too deeply nested: split it.") from exc
    try:
        with decimal.localcontext(_CONTEXT) as context:
            result = _evaluate(tree, expression)
    except decimal.DivisionByZero as exc:
        raise CalculationError("Division by zero.") from exc
    except decimal.Overflow as exc:
        raise CalculationError("Result too large.") from exc
    except decimal.InvalidOperation as exc:
        raise CalculationError(
            "Undefined result (e.g. 0 / 0, modulo by zero, "
            "or a fractional power of a negative number)."
        ) from exc
    except RecursionError as exc:
        raise CalculationError("Expression too deeply nested: split it.") from exc
    return expression, _format(result, inexact=bool(context.flags[decimal.Inexact]))
