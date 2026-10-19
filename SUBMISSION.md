# HW4 — submission

**AI assistance:** <!-- what you used, and for what. "None" is an answer too. -->

---

## Part A — Plan on paper (Easy)

> Commit this whole part before any `.py` file exists.

### A1 — The steps

| # | Step | What goes in (types) | What comes out (types) | When it goes wrong | Tool, loop, or model? |
|---|------|----------------------|------------------------|--------------------|-----------------------|
| 1 | Understand the question | `question: str` | `districts: list[str]`, `quantity: str`, `operation: str` | Question names a district that does not exist → handled in step 2 | Model |
| 2 | Resolve district name | `name: str` | `district_id: str` (canonical name) | No match → error with close matches. Two similar names (TODO: which pair) → error listing both, no guessing | Tool (`lookup`) |
| 3 | Pick the valid profile | `district_id: str` | one current profile (`dict`) | Only an archived profile exists → error. A correction notice exists (NR-16) → apply it | Tool (`lookup`) |
| 4 | Read one field | `profile: dict`, `field: str` | `value: float`, `unit: str`, `source: str` | Field missing, number unreadable, unknown unit → error dict, never a crash | Tool (`lookup`) |
| 5 | Normalise units | `value: float`, `unit: str` | `value: float` in the common unit | Unknown unit → error. TODO: one district reports water use in a different unit | Model (arithmetic via `calculate`) |
| 6 | Arithmetic | `expression: str` | `result: float` | Division by zero, bad syntax, forbidden syntax, huge exponent → error dict | Tool (`calculate`) |
| 7 | Compare and decide | numbers (`float`) | name (or yes/no) `str` + number `float` | Equal values or tie → say so | Model |
| 8 | Format the answer | name `str`, number `float` | `"ANSWER: <name> \| <number>"` (`str`) | Line missing or malformed → counted as unanswered | Loop (checks) + Model (writes) |

**How the steps connect: question → 1 (model) → 2 → 3 → 4 [all inside one `lookup` call, once per district per field]
→ 5 (model) → 6 `calculate` → 7 (model) → 8 ANSWER line.
The loop sits between the model and the tools: it parses `arguments`, runs the tool,
answers every `tool_call_id`, enforces the round limit and writes the log.**

<!-- which step feeds which: a list, an ASCII diagram, or an image committed to the repo -->

**What I am assuming:**
- Only current (non-archived) profiles are used: TODO which year / which two are archived.
- A correction notice (NR-16) overrides the value it corrects.
- Water use is converted to one common unit before comparing: TODO the unit and factor.
- Numbers are not rounded until the last step; rounding follows `decimals` in the question.
- District names are matched case-insensitively; a typo is fixed only if exactly one close match exists.

<!-- census year, archived profiles, corrections, units, where rounding happens, ... -->

### A2 — The two tools

#### `lookup`
```json
{
  "type": "function",
  "function": {
    "name": "lookup",
    "description": "Look up ONE fact about ONE district of the Nine Rivers Region from the official documents. Returns the value, its unit and the source document id. Always uses the current (non-archived) profile and applies later corrections. Call once per district per field. Check the 'unit' field before comparing districts.",
    "parameters": {
      "type": "object",
      "properties": {
        "district": {"type": "string", "description": "District name, e.g. 'Brightwater'."},
        "field": {"type": "string", "enum": ["population", "area_km2", "water_use"], "description": "TODO: replace with the real field names."}
      },
      "required": ["district", "field"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|------|-----------------------|
| success | `{"district": "Brightwater", "field": "population", "value": 44675, "unit": "people", "source": "NR-xx", "note": ""}` |
| corrected value | same as success, with `"note": "corrected by NR-16"` |
| unknown district | `{"error": "no district named Ossbrige; did you mean Ossbridge or Ossford?"}` |
| two similar names | `{"error": "ambiguous: X or Y; call again with the exact name"}` (TODO: real names) |
| only archived profile | `{"error": "only an archived profile exists for X; no current data"}` |
| unknown field | `{"error": "unknown field 'x'; valid fields: ..."}` |
| unreadable number | `{"error": "could not read a number for field 'x' in NR-xx"}` |

**Worst thing it could do with strange or dangerous input: silently return an old (archived) value, which would give a wrong answer. I prevent this by excluding archived profiles in code. It cannot read files, because the corpus is loaded once into memory. It returns one fact, not whole documents, so it cannot flood the context.**

#### `calculate`
```json
{
  "type": "function",
  "function": {
    "name": "calculate",
    "description": "Evaluate an arithmetic expression exactly and return the result. Supports numbers, + - * / ** % and parentheses only. Use it for ALL arithmetic (density, differences, unit conversion); do not calculate in your head. Example: '44675 / 921.4'.",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {"type": "string", "description": "Arithmetic expression, e.g. '48317 * 1.0947'."}
      },
      "required": ["expression"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|------|-----------------------|
| success | `{"result": 52891.7}` |
| syntax error | `{"error": "invalid expression"}` |
| forbidden syntax (names, calls, attributes) | `{"error": "not allowed: Call"}` |
| division by zero | `{"error": "division by zero"}` |
| huge exponent or very long input | `{"error": "exponent too large"}` / `{"error": "expression too long"}` |

**Worst thing it could do with strange or dangerous input: with `eval`, it could run any Python code (for example `__import__('os').system(...)`). I prevent this by parsing with `ast` and allowing only numeric constants and `+ - * / ** %`. Limits on input length and exponent size stop `9**9**9` from freezing the program.**

### A3 — Q-09 by hand
[
  {"role": "user", "content": "<TODO: Q-09 text>"},
  {"role": "assistant", "tool_calls": [
    {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"<TODO>\", \"field\": \"<TODO>\"}"}},
    {"id": "call_2", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"<TODO>\", \"field\": \"<TODO>\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_1", "content": "{\"value\": <TODO>, \"unit\": \"<TODO>\", \"source\": \"NR-05\"}"},
  {"role": "tool", "tool_call_id": "call_2", "content": "{\"value\": <TODO>, \"unit\": \"<TODO>\", \"source\": \"NR-05\", \"note\": \"corrected by NR-16\"}"},
  {"role": "assistant", "tool_calls": [
    {"id": "call_3", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"<TODO>\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_3", "content": "{\"result\": <TODO>}"},
  {"role": "assistant", "content": "<TODO short explanation>\nANSWER: <name> | <number>"}
]

**My arithmetic: TODO. Write the calculation step by step, then check that it equals value (rounded to decimals) for Q-09. Use the correct answer in the file only to check my work, never inside a prompt.**

### A4 — Why I split it this way
I could have made one big answer_question(question) tool that does the lookup, the arithmetic and the comparison inside my own code. I did not choose it because it hides all the work from the model, so S3 would no longer test whether the model can use tools: it would just be my code answering. It is also brittle, because every new question type needs new code. With two small tools, the model decides what to look up and which numbers to compute, and I can inspect every step in the logs. Keeping calculate separate from lookup also gives me one safe, reusable arithmetic tool instead of many one-off formulas.

## Part B — Build it and run it (Medium)

### What I changed from Part A while coding

<!-- what changed in your plan, and why. "None" is an answer too. -->

### B2 — Tests

```text
<!-- pytest output -->
```

### B3 — The loop

- Round limit, and why:
- Where the logs are:
- Real Q-09 conversation compared with my A3 version, what is different:

### B4 — Three strategies

**What I kept the same:**

<!-- model, temperature, k, prompts, answer format, anything else -->

**My rule for a correct answer** (written before the first full run):

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | | | | | | | |
| 1 | S2 think and vote (k = ) | | | | | | | |
| 1 | S3 tools | | | | | | | |
| 2 | S1 direct | | | | | | | |
| 2 | S2 think and vote (k = ) | | | | | | | |
| 2 | S3 tools | | | | | | | |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | | | |
| Q-02 | | | |
| Q-03 | | | |
| Q-04 | | | |
| Q-05 | | | |
| Q-06 | | | |
| Q-07 | | | |
| Q-08 | | | |
| Q-09 | | | |
| Q-10 | | | |
| Q-11 | | | |
| Q-12 | | | |
| Q-13 | | | |
| Q-14 | | | |
| Q-15 | | | |
| Q-16 | | | |
| Q-17 | | | |
| Q-18 | | | |
| Q-19 | | | |
| Q-20 | | | |

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| | | | | |

### C2 — Three mistakes explained

### C3 — Which strategy I would use, and what would change it

### C4 — How sure I can be

### Final questions

1.
2.
3.
4.
5.
6.
7.
8.
