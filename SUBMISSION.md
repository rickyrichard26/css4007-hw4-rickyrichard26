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
```json
[
  {"role": "user", "content": "TODO paste the exact Q-09 text here"},
  {"role": "assistant", "tool_calls": [
    {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Brightwater\", \"field\": \"population\"}"}},
    {"id": "call_2", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Brightwater\", \"field\": \"area_km2\"}"}},
    {"id": "call_3", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Millbrook\", \"field\": \"population\"}"}},
    {"id": "call_4", "type": "function", "function": {"name": "lookup", "arguments": "{\"district\": \"Millbrook\", \"field\": \"area_km2\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_1", "content": "{\"value\": 44675, \"unit\": \"people\", \"source\": \"NR-05\"}"},
  {"role": "tool", "tool_call_id": "call_2", "content": "{\"value\": 921.4, \"unit\": \"km2\", \"source\": \"NR-16\", \"note\": \"corrected by NR-16; NR-05 said 912.4\"}"},
  {"role": "tool", "tool_call_id": "call_3", "content": "{\"value\": 37203, \"unit\": \"people\", \"source\": \"NR-11\"}"},
  {"role": "tool", "tool_call_id": "call_4", "content": "{\"value\": 758.6, \"unit\": \"km2\", \"source\": \"NR-11\"}"},
  {"role": "assistant", "tool_calls": [
    {"id": "call_5", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"44675 / 921.4\"}"}},
    {"id": "call_6", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"37203 / 758.6\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_5", "content": "{\"result\": 48.486}"},
  {"role": "tool", "tool_call_id": "call_6", "content": "{\"result\": 49.0417}"},
  {"role": "assistant", "tool_calls": [
    {"id": "call_7", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"49.0417 - 48.486\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "call_7", "content": "{\"result\": 0.5557}"},
  {"role": "assistant", "content": "Millbrook is denser: about 49.04 people per km2 against 48.49 for Brightwater, a difference of 0.56 people per km2.\nANSWER: Millbrook | 0.56"}
]
```

**My arithmetic:**
- Brightwater uses the corrected area from NR-16 (921.4, not the 912.4 printed in NR-05): 44,675 / 921.4. Since 921.4 × 48 = 44,227.2 and the remainder is 447.8, which is 0.486 of 921.4, the density is about 48.486 people/km2.
- Millbrook (NR-11): 37,203 / 758.6. Since 758.6 × 49 = 37,171.4 and the remainder is 31.6, which is 0.0417 of 758.6, the density is about 49.042 people/km2.
- Difference: 49.042 − 48.486 = 0.556, which rounds to 0.56. Millbrook is denser.
- If I had used the wrong area 912.4, Brightwater would be about 48.96 and the difference only about 0.08, so the correction notice changes the answer.

### A4 — Why I split it this way
I could have made one big answer_question(question) tool that does the lookup, the arithmetic and the comparison inside my own code. I did not choose it because it hides all the work from the model, so S3 would no longer test whether the model can use tools: it would just be my code answering. It is also brittle, because every new question type needs new code. With two small tools, the model decides what to look up and which numbers to compute, and I can inspect every step in the logs. Keeping calculate separate from lookup also gives me one safe, reusable arithmetic tool instead of many one-off formulas.

## Part B — Build it and run it (Medium)

### What I changed from Part A while coding

<!-- what changed in your plan, and why. "None" is an answer too. -->

### B2 — Tests

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.7.0 -- D:\css4007-hw4-rickyrichard26\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\css4007-hw4-rickyrichard26
plugins: anyio-4.15.1
collecting ... collected 35 items

tests/test_tools.py::test_calculate_required_example PASSED              [  2%]
tests/test_tools.py::test_calculate_basic_and_precedence PASSED          [  5%]
tests/test_tools.py::test_calculate_division_by_zero PASSED              [  8%]
tests/test_tools.py::test_calculate_invalid_syntax PASSED                [ 11%]
tests/test_tools.py::test_calculate_refuses_import_call PASSED           [ 14%]
tests/test_tools.py::test_calculate_refuses_attribute_access PASSED      [ 17%]
tests/test_tools.py::test_calculate_refuses_huge_power PASSED            [ 20%]
tests/test_tools.py::test_calculate_refuses_names_and_strings PASSED     [ 22%]
tests/test_tools.py::test_calculate_refuses_too_long_and_non_string PASSED [ 25%]
tests/test_tools.py::test_calculate_refuses_booleans PASSED              [ 28%]
tests/test_tools.py::test_lookup_finds_2025_number PASSED                [ 31%]
tests/test_tools.py::test_lookup_is_case_insensitive PASSED              [ 34%]
tests/test_tools.py::test_lookup_applies_correction_notice PASSED        [ 37%]
tests/test_tools.py::test_lookup_misspelled_name PASSED                  [ 40%]
tests/test_tools.py::test_lookup_two_similar_names_stay_separate PASSED  [ 42%]
tests/test_tools.py::test_lookup_ignores_archived_profiles PASSED        [ 45%]
tests/test_tools.py::test_lookup_water_unit_differs_for_lindenmoor PASSED [ 48%]
tests/test_tools.py::test_lookup_handles_missing_spaces_in_profiles PASSED [ 51%]
tests/test_tools.py::test_lookup_uses_numbers_not_wording PASSED         [ 54%]
tests/test_tools.py::test_lookup_water_tariff PASSED                     [ 57%]
tests/test_tools.py::test_lookup_unknown_field_and_wrong_scope PASSED    [ 60%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Ossbridge] PASSED [ 62%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Ossford] PASSED [ 65%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Tarnvale] PASSED [ 68%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Kelmarsh] PASSED [ 71%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Brightwater] PASSED [ 74%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Stonecairn] PASSED [ 77%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Harrowfield] PASSED [ 80%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Lindenmoor] PASSED [ 82%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Redfen] PASSED [ 85%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Ashgrove] PASSED [ 88%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Millbrook] PASSED [ 91%]
tests/test_tools.py::test_lookup_every_field_parses_for_every_district[Coldharbour] PASSED [ 94%]
tests/test_tools.py::test_lookup_never_raises_on_bad_types PASSED        [ 97%]
tests/test_tools.py::test_run_tool_rejects_bad_arguments PASSED          [100%]

============================= 35 passed in 0.06s ==============================
```

### B3 — The loop

- Round limit, and why: 8. Q-09 needed 4 rounds: one round with 4 parallel `lookup` calls, two rounds of `calculate`, and one round for the final answer. A question with a retry after an error needs a few more, so 8 is double what Q-09 needed and normal questions are never cut off. If the model keeps repeating a bad call, the loop stops after 8 API calls and the question counts as unanswered, so it cannot run up cost. TODO after the full runs: write the largest number of rounds I saw in the S3 logs (which question, how many) and say whether 8 was enough.
- Where the logs are: in `outputs/`. `S3_run1.json` and `S3_run2.json` contain, for every question, the number of rounds, each tool call with its arguments, result and duration, and the token usage. The first test run on Q-09 alone is `outputs/S3_run1_partial.json`.
- Real Q-09 conversation compared with my A3 version, what is different: The real run used 4 rounds and 7 tool calls (3,087 input tokens, 244 output tokens, 14.9 s). In round 1 the model asked for all four lookups at once (population and area of Brightwater and Millbrook). In round 2 it called `calculate` for each density (44675 / 921.4 and 37203 / 758.6). In round 3 it called `calculate` once more for the difference, by repeating both divisions in one expression instead of subtracting my two results. Round 4 was the final answer, `ANSWER: Millbrook | 0.56`. The Brightwater area came back as 921.4 from NR-16, with a note that NR-05 said 912.4, so the correction notice worked. Differences from A3: TODO (edit this to match what you wrote in A3, for example the model batched the lookups instead of calling them one by one, the third `calculate` call was redundant, and the model did the rounding to 0.56 itself because `calculate` returns the unrounded 0.5557). I completed the A3 walkthrough after my first test run of Q-09, so it is not an independent prediction.

### B4 — Three strategies

**What I kept the same: the model (gpt-5.6-luna through the Chat Completions API), the same 20 questions in the same order, the same final-line format `ANSWER: <name or yes/no> | <number>` read by the same parser, and the same grader. S1 and S2 get the text of all 17 documents in the system message; S2 only adds "think step by step" and samples k = 5 times (temperature: TODO write what you found, accepted or default). S3 gets no documents, only the two tools (`lookup`, `calculate`) with a round limit of 8. Only the question text is sent to the model; the expected answers are used only by the grader.
**

<!-- model, temperature, k, prompts, answer format, anything else -->

**My rule for a correct answer** (written before the first full run): the name matches the expected answer exactly (ignoring upper/lower case), and the number equals the expected value rounded to `decimals`, with a difference of at most one in the last digit allowed. If there is no parseable `ANSWER:` line, the question counts as unanswered and wrong.

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | 11 | 1 | 43,600 | 1,408 | 1.7 | 36.0 | 0.0104 |
| 1 | S2 think and vote (k = ) | 13 | 0 | 218,900 | 7,277 | 9.0 | 181.4 | 0.0525 |
| 1 | S3 tools | 20 | 0 | 50,837 | 4,484 | 5.5 | 114.6 | 0.0155 |
| 2 | S1 direct | 12 | 0 | 43,600 | 1,325	| 1.7 | 36.3 | 0.0103 |
| 2 | S2 think and vote (k = ) | 14 | 0 | 218,900 | 7,193 | 8.3 | 165.1 | 0.0524 |
| 2 | S3 tools | 20 | 0 | 49,961 | 4,500 | 5.4 | 113.4 | 0.0154 |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✓ | ✓ | ✓ |
| Q-02 | ✓ | ✓ | ✓ |
| Q-03 | ✗ | ✓ | ✓ |
| Q-04 | ✓ | ✓ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✓ | ✓ | ✓ |
| Q-07 | ✓ | ✗ | ✓ |
| Q-08 | ✗ | ✓ | ✓ |
| Q-09 | ✓ | ✓ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✗ | ✗ | ✓ |
| Q-12 | ✗ | ✓ | ✓ |
| Q-13 | ✗ | ✗ | ✓ |
| Q-14 | ✓ | ✓ | ✓ |
| Q-15 | ✓ | ✗ | ✓ |
| Q-16 | ✓ | ✓ | ✓ |
| Q-17 | ✗ | ✗ | ✓ |
| Q-18 | ✗ | ✓ | ✓ |
| Q-19 | ✓ | ✓ | ✓ |
| Q-20 | ✗ (unanswered | ✗ | ✓ |

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| Q-17 | ? | ? | harrowfield,884.46 | harrowfield,884.46 |
| Q-18 | ? | ? | brightwater, 72.45615 | brightwater, 72.45615 |

### C2 — Three mistakes explained

### C3 — Which strategy I would use, and what would change it
I would use S3. It was 20/20 in both runs, at about 1.5× the cost of S1 ($0.0155 vs $0.0104). S1 is cheapest and fastest (median 1.7 s) but only 11–12/20. S2 costs about 5× S1 ($0.052) for only +2 correct, and it still fails on questions where the model makes the same mistake every time, so voting cannot fix it. What would change my choice: if the corpus were much larger, S1 and S2 would get far more expensive because every call carries all documents; if latency mattered more than accuracy, S1 would win; if the tools were unreliable or slow, S3 would lose its edge. 

### C4 — How sure I can be
With 20 questions, one question is 5 percentage points. S1 moved 11→12 and S2 13→14 between runs, so a 1-question gap is within noise. The gap between S3 (20/20) and S1/S2 (11–14) is much larger than that. S3 still could not prove 100% accuracy; it only shows no errors in 40 tries (2 runs × 20 questions). Also, the questions are the same in both runs, so the two runs are not independent evidence.

### Final questions

1.
2.
3.
4.
5.
6.
7.
8.
