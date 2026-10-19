"""Two tools for the LLM: lookup (facts from the corpus) and calculate (safe arithmetic)."""
import ast
import difflib
import json
import operator
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# --------------------------------------------------------------------------
# calculate: arithmetic via ast, NO eval/exec
# --------------------------------------------------------------------------
MAX_EXPR_LEN = 200      # also bounds nesting depth
MAX_EXPONENT = 100      # stops 9**9**9 before it is computed
MAX_ABS_RESULT = 1e100  # "very large number" limit

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


class CalcError(Exception):
    pass


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    # bool is a subclass of int, so check the exact type
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise CalcError("exponent too large")
        try:
            result = _BIN_OPS[type(node.op)](left, right)
        except ZeroDivisionError:
            raise CalcError("division by zero")
        except OverflowError:
            raise CalcError("number too large")
        if isinstance(result, complex) or abs(result) > MAX_ABS_RESULT:
            raise CalcError("number too large")
        return result
    raise CalcError(f"not allowed: {type(node).__name__}")


def calculate(expression: str) -> dict:
    """Return {"result": number} or {"error": message}. Never raises."""
    try:
        if not isinstance(expression, str):
            return {"error": "expression must be a string"}
        if len(expression) > MAX_EXPR_LEN:
            return {"error": "expression too long"}
        try:
            tree = ast.parse(expression.strip(), mode="eval")
        except SyntaxError:
            return {"error": "invalid expression"}
        return {"result": _eval(tree)}
    except CalcError as e:
        return {"error": str(e)}
    except RecursionError:
        return {"error": "expression too deeply nested"}
    except Exception as e:  # last resort: a tool must never crash the loop
        return {"error": f"internal error: {type(e).__name__}"}


# --------------------------------------------------------------------------
# lookup: TODO, depends on the real corpus. Fill the marked parts.
# --------------------------------------------------------------------------
_CORPUS = None


def load_corpus() -> dict:
    """Read data/corpus.jsonl once. Returns {doc_id: {"id", "title", "text"}}."""
    global _CORPUS
    if _CORPUS is None:
        docs = {}
        with open(DATA_DIR / "corpus.jsonl", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    docs[d["id"]] = d
        _CORPUS = docs
    return _CORPUS


FIELDS = ["population", "area_km2", "water_use"]  # TODO: real field names


def lookup(district: str, field: str) -> dict:
    """Return one fact about one district, or {"error": message}. Never raises."""
    try:
        if not isinstance(district, str) or not isinstance(field, str):
            return {"error": "district and field must be strings"}
        if field not in FIELDS:
            return {"error": f"unknown field '{field}'; valid fields: {', '.join(FIELDS)}"}
        docs = load_corpus()

        # TODO 1: build {district name: [profile docs]} from NR-01..NR-12.
        #   Mark which profiles are archived; keep the corrections from NR-16.
        # TODO 2: resolve `district` (case-insensitive). If no exact match, use
        #   difflib.get_close_matches(district, names, n=3). If there are two
        #   similar names, return an "ambiguous" error; never guess.
        # TODO 3: pick the non-archived profile (error if only archived exists),
        #   read `field`, apply any correction, return:
        #   {"district": ..., "field": field, "value": float, "unit": str,
        #    "source": "NR-xx", "note": ""}
        return {"error": "lookup not implemented yet"}
    except Exception as e:
        return {"error": f"internal error: {type(e).__name__}"}


# --------------------------------------------------------------------------
# Definitions sent to the model (must match Part A) and the dispatcher
# --------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": (
                "Look up ONE fact about ONE district of the Nine Rivers Region from the "
                "official documents. Returns the value, its unit and the source document "
                "id. Always uses the current (non-archived) profile and applies later "
                "corrections. Call once per district per field. Check the 'unit' field "
                "before comparing districts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {"type": "string", "description": "District name, e.g. 'Brightwater'."},
                    "field": {"type": "string", "enum": FIELDS, "description": "Which fact to read."},
                },
                "required": ["district", "field"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate an arithmetic expression exactly and return the result. Supports "
                "numbers, + - * / ** % and parentheses only. Use it for ALL arithmetic "
                "(density, differences, unit conversion); do not calculate in your head. "
                "Example: '44675 / 921.4'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Arithmetic expression, e.g. '48317 * 1.0947'."}
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        },
    },
]


def run_tool(name: str, args) -> dict:
    """Validate arguments, then run the tool. Never raises."""
    if not isinstance(args, dict):
        return {"error": "arguments must be a JSON object"}
    if name == "lookup":
        if set(args) != {"district", "field"}:
            return {"error": "lookup needs exactly: district, field"}
        return lookup(args["district"], args["field"])
    if name == "calculate":
        if set(args) != {"expression"}:
            return {"error": "calculate needs exactly: expression"}
        return calculate(args["expression"])
    return {"error": f"unknown tool '{name}'"}