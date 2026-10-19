import ast
import difflib
import json
import operator
import re
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
# lookup: reads facts from data/corpus.jsonl (built once, in memory)
# --------------------------------------------------------------------------
_CORPUS = None
_INDEX = None


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


def _num(s: str):
    s = s.replace(",", "")
    return float(s) if "." in s else int(s)


# field -> (unit, [regexes]). The profiles use three sentence templates and some
# have missing spaces ("593.8square", "recorded90,212"), so every pattern uses \s*.
_FIELD_SPECS = {
    "population_2025": ("people", [
        r"recorded\s*(\d[\d,]*)\s*residents",
        r"in 2020 and\s*(\d[\d,]*)\s*in 2025",
        r"2025 census counted\s*(\d[\d,]*)\s*residents"]),
    "population_2020": ("people", [
        r"2020 census had recorded\s*(\d[\d,]*)",
        r"Census population:\s*(\d[\d,]*)\s*in 2020",
        r"up from\s*(\d[\d,]*)\s*at the 2020 census"]),
    "area_km2": ("km2", [r"(\d[\d,]*\.\d+)\s*square kilometres"]),
    "budget_2025_million_tenge": ("million tenge", [r"(\d[\d,]*\.\d+)\s*million tenge"]),
    "schools": ("schools", [r"(\d+)\s*schools"]),
    "pupils": ("pupils", [r"(?:attended by|enrolled|with)\s*(\d[\d,]*)\s*pupils"]),
    "road_km": ("km", [r"(\d[\d,]*\.\d+)\s*km"]),
    "founded_year": ("year", [r"[Ff]ounded in\s*(\d{4})"]),
}
# water_use is special: the unit differs between profiles (megalitres vs cubic metres)
_WATER_PATTERNS = [(r"(\d[\d,]*)\s*megalitres", "megalitres"),
                   (r"(\d[\d,]*)\s*cubic metres", "cubic metres")]

FIELDS = list(_FIELD_SPECS) + ["water_use"]
REGION_FIELDS = ["water_tariff_2025", "water_tariff_2024", "m3_per_megalitre"]
ALL_FIELDS = FIELDS + REGION_FIELDS
REGION_NAMES = {"region", "nine rivers region", "nine rivers"}


def _build_index() -> dict:
    current, archived, corrections, region = {}, {}, {}, {}
    for d in load_corpus().values():
        title, text = d["title"], d["text"]
        m = re.match(r"(\w+) district profile", title)
        if m:
            if "ARCHIVED" in title.upper():
                archived.setdefault(m.group(1), []).append(d["id"])
            else:
                current[m.group(1)] = d
            continue
        m = re.match(r"Correction notice\s*-\s*(\w+)", title)
        if m:
            c = re.search(r"correct area is\s*(\d[\d,]*\.\d+)\s*square kilometres", text)
            w = re.search(r"gives the district's area as\s*(\d[\d,]*\.\d+)", text)
            if c:
                corrections[(m.group(1), "area_km2")] = {
                    "value": _num(c.group(1)), "source": d["id"],
                    "old": _num(w.group(1)) if w else None}
            continue
        if "tariff" in title.lower():
            for key, pat, unit in [
                ("water_tariff_2025", r"regional household water tariff is\s*(\d+(?:\.\d+)?)", "tenge per cubic metre"),
                ("water_tariff_2024", r"2024 tariff was\s*(\d+(?:\.\d+)?)", "tenge per cubic metre"),
                ("m3_per_megalitre", r"One megalitre is\s*(\d[\d,]*)\s*cubic metres", "cubic metres per megalitre"),
            ]:
                r = re.search(pat, text)
                if r:
                    region[key] = {"value": _num(r.group(1)), "unit": unit, "source": d["id"]}
    return {"current": current, "archived": archived, "corrections": corrections, "region": region}


def _index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    return _INDEX


def _clean_name(name: str) -> str:
    key = name.strip().lower()
    return key[: -len(" district")].strip() if key.endswith(" district") else key


def _suggestions(key: str, names: list) -> list:
    low = {n.lower(): n for n in names}
    found = [low[k] for k in low if len(key) >= 3 and k.startswith(key)]
    for k in difflib.get_close_matches(key, list(low), n=3, cutoff=0.6):
        if low[k] not in found:
            found.append(low[k])
    return found[:3]


def lookup(district: str, field: str) -> dict:
    """Return one fact about one district, or {"error": message}. Never raises."""
    try:
        if not isinstance(district, str) or not isinstance(field, str):
            return {"error": "district and field must be strings"}
        if field not in ALL_FIELDS:
            return {"error": f"unknown field '{field}'; valid fields: {', '.join(ALL_FIELDS)}"}
        idx = _index()
        key = _clean_name(district)

        # region-wide facts (water tariff) live in NR-15
        if key in REGION_NAMES or field in REGION_FIELDS:
            if key in REGION_NAMES and field not in REGION_FIELDS:
                return {"error": f"'Region' only has: {', '.join(REGION_FIELDS)}; "
                                 "use a district name for other fields"}
            if field in REGION_FIELDS and key not in REGION_NAMES:
                return {"error": f"'{field}' is region-wide: call with district 'Region'"}
            r = idx["region"].get(field)
            if r is None:
                return {"error": f"could not read '{field}' in the corpus"}
            return {"district": "Region", "field": field, "value": r["value"],
                    "unit": r["unit"], "source": r["source"], "note": ""}

        names = sorted(idx["current"])
        match = next((n for n in names if n.lower() == key), None)
        if match is None:
            for a in idx["archived"]:
                if a.lower() == key:
                    return {"error": f"only an archived profile exists for {a}; no current data"}
            sug = _suggestions(key, names)
            hint = (f"did you mean {' or '.join(sug)}?" if sug
                    else f"valid districts: {', '.join(names)}")
            return {"error": f"no district named {district.strip()}; {hint}"}

        doc = idx["current"][match]
        text = doc["text"]
        note = ""
        if field == "water_use":
            hit = None
            for pat, unit in _WATER_PATTERNS:
                m = re.search(pat, text)
                if m:
                    hit = (_num(m.group(1)), unit)
                    break
            if hit is None:
                return {"error": f"could not read a number for field '{field}' in {doc['id']}"}
            value, unit = hit
            if unit != "megalitres":
                note = f"reported in {unit}, not megalitres"
        else:
            unit, pats = _FIELD_SPECS[field]
            value = None
            for pat in pats:
                m = re.search(pat, text)
                if m:
                    value = _num(m.group(1))
                    break
            if value is None:
                return {"error": f"could not read a number for field '{field}' in {doc['id']}"}

        source = doc["id"]
        corr = idx["corrections"].get((match, field))
        if corr:
            value, source = corr["value"], corr["source"]
            note = f"corrected by {corr['source']}; {doc['id']} originally said {corr['old']}"
        return {"district": match, "field": field, "value": value,
                "unit": unit, "source": source, "note": note}
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
                "before comparing districts. For the region-wide water tariff use district 'Region' with "
                "field water_tariff_2025 (tenge per cubic metre) or m3_per_megalitre."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {"type": "string", "description": "District name, e.g. 'Brightwater'."},
                    "field": {"type": "string", "enum": ALL_FIELDS, "description": "Which fact to read."},
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
