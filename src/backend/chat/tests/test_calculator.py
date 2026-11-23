"""Tests for chat.calculator: exact arithmetic on model-written expressions."""

import pytest

from chat.calculator import CalculationError, calculate


def _result(expression: str) -> str:
    return calculate(expression)[1]


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("0.1 + 0.2", "0.3"),
        ("1056564.58 + 303695.03", "1360259.61"),
        ("149.90 * 1.2", "179.88"),
        ("round((1250.40 - 980) / 980 * 100, 2)", "27.59"),
        ("1 / 3", "0.3333333333333333333333333333"),
        ("1 / 3 * 3", "1"),
        ("10 // 3", "3"),
        ("-7 // 3", "-3"),
        ("-7 % 3", "2"),
        ("7.5 % 2", "1.5"),
        ("2 ** 10", "1024"),
        ("2 ** 100", "1267650600228229401496703205376"),
        ("2 ** -1", "0.5"),
        ("2 ** 0.5", "1.414213562373095048801688724"),
        ("sqrt(16)", "4"),
        ("abs(-3.5)", "3.5"),
        ("min(4, 2.5, 9)", "2.5"),
        ("max([4, 2.5, 9])", "9"),
        ("sum(12, 15.5, 9) / 3", "12.16666666666666666666666667"),
        ("sum([1, 2, 3.5])", "6.5"),
        ("10 ** 100", "1e+100"),
        ("-(-5)", "5"),
        ("1 - 1", "0"),
        ("0.12345678901234567890 * 1", "0.1234567890123456789"),
        ("1234567890.123456789 + 0", "1234567890.123456789"),
        ("1e400", "1e+400"),
        ("1e-400", "1e-400"),
        ("1_000.5 * 2", "2001"),
        (".5 + 1.", "1.5"),
    ],
)
def test_calculate(expression, expected):
    """Expressions are computed exactly in decimal, with Python's // and % semantics."""
    assert _result(expression) == expected


@pytest.mark.parametrize(
    "expression,same_as",
    [
        ("sum(1 / 3, 1 / 3)", "1 / 3 + 1 / 3"),
        ("abs(-1 / 3)", "1 / 3"),
        ("sum(1 / 3, 1 / 3) * 3", "(1 / 3 + 1 / 3) * 3"),
    ],
)
def test_functions_use_the_calculator_precision(expression, same_as):
    """sum() and abs() compute at the same precision as the operators."""
    assert _result(expression) == _result(same_as)


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("round(2.5)", "3"),
        ("round(-2.5)", "-3"),
        ("round(1.005, 2)", "1.01"),
        ("round(1234.5, -2)", "1200"),
    ],
)
def test_round_is_half_up(expression, expected):
    """round() rounds half up like people do, not half to even like Python's round."""
    assert _result(expression) == expected


def test_calculate_returns_the_expression_as_written():
    """The expression comes back as written (stripped) so the answer can be checked."""
    assert calculate("  (1+2)*1e400 ")[0] == "(1+2)*1e400"


@pytest.mark.parametrize(
    "expression,message",
    [
        ("1/0", "Division by zero."),
        ("5 % 0", "Division by zero."),
        ("0/0", "Undefined result"),
        ("(-8) ** 0.5", "Undefined result"),
        ("9 ** 9 ** 9", "Result too large."),
        ("1e9999999", "Result too large."),
        ("sqrt(-1)", "sqrt() of a negative number"),
        ("round(1.5, 0.5)", "round() digits must be an integer"),
        ("round(10 ** 40, 2)", "more than 34 significant digits"),
        ("1,5", "Unexpected comma. Use '.' as decimal separator"),
        ("1 234,56", "Invalid expression"),
        ("15%", "write a percentage as a division"),
        ("", "Invalid expression"),
        ("x + 1", "Unsupported syntax (Name)."),
        ("True + 1", "Only numbers are allowed."),
        ("'a' * 3", "Only numbers are allowed."),
        ("1j", "Only numbers are allowed."),
        ("min()", "Wrong number of arguments for min()."),
        ("round(2.5, digits=1)", "Keyword arguments are not supported."),
        ("cos(1)", "Unknown function. Available: round, abs, sqrt, min, max, sum."),
        ("1 if 1 else 2", "Unsupported syntax (IfExp)."),
        ("1 < 2", "Unsupported syntax (Compare)."),
        ("1" * 501, "Expression too long"),
        ("(" * 240 + "1" + ")" * 240, "Invalid expression"),
    ],
)
def test_invalid_expressions_explain_the_fix(expression, message):
    """Errors are CalculationError with a message the model can act on."""
    with pytest.raises(CalculationError) as exc_info:
        calculate(expression)

    assert message in str(exc_info.value)


@pytest.mark.parametrize(
    "expression",
    ["secret_name + 1", "'secret text' * 2", "secret_function(1)", "secret_name.attr"],
)
def test_error_messages_do_not_quote_the_expression(expression):
    """Error messages are logged on retry, so they never carry model-written text."""
    with pytest.raises(CalculationError) as exc_info:
        calculate(expression)

    assert "secret" not in str(exc_info.value)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "(1).__class__",
        "[].__class__.__base__",
        "open('/etc/passwd')",
        "eval('1')",
        "(lambda: 1)()",
        "[x for x in (1, 2)]",
        "{'a': 1}",
    ],
)
def test_code_cannot_be_reached(expression):
    """Names, attributes, lambdas, comprehensions and other calls are rejected."""
    with pytest.raises(CalculationError):
        calculate(expression)
