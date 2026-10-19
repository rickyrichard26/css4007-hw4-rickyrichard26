import os
import copy
import json
import re
import time
from collections import Counter

from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOLS, load_corpus, run_tool

load_dotenv()  # must run before the client is created

if os.environ.get("OPENROUTER_API_KEY"):
    PROVIDER = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1"
    client = OpenAI(
        base_url=BASE_URL,
        api_key=os.environ["OPENROUTER_API_KEY"]
    )
    MODEL = "openai/gpt-5.6-luna"
else:
    PROVIDER = "openai"
    BASE_URL = "https://api.openai.com/v1"
    client = OpenAI()
    MODEL = "gpt-5.6-luna"

K = 5
S2_TEMPERATURE = 1.0
MAX_ROUNDS = 8

FORMAT_RULE = (
    "End your reply with exactly one final line in this format:\n"
    "ANSWER: <name or yes/no> | <number>"
)

SYSTEM_DIRECT = (
    "You answer questions about the Nine Rivers Region using ONLY the documents below. "
    "Some profiles are archived (do not use them) and some facts are corrected by later "
    "notices. " + FORMAT_RULE
)
SYSTEM_COT = SYSTEM_DIRECT + "\nThink step by step before the final line."
SYSTEM_TOOLS = (
    "You answer questions about the Nine Rivers Region. You have no documents: use the "
    "tools lookup and calculate to get facts and do arithmetic. " + FORMAT_RULE
)

_ANSWER_RE = re.compile(
    r"ANSWER:\s*(.+?)\s*\|\s*([-+]?[\d.,]+)", re.IGNORECASE,
    )

_TEMP_OK = True


def docs_text() -> str:
    return "\n\n".join(f"[{d['id']}] {d['title']}\n{d['text']}" for d in load_corpus().values())


def parse_answer(text):
    """Return (name, number) from the last ANSWER line, or None."""
    matches = _ANSWER_RE.findall(text or "")
    if not matches:
        return None
    name, num = matches[-1]
    try:
        name = name.strip().strip("*`_ ").lower()
        return name, float(num.replace(",", "").rstrip(".,"))
    except ValueError:
        return None


def _new_usage():
    return {
        "input": 0,
        "output": 0,
        "seconds": 0.0,
        "calls": 0
        }


def _chat(usage, **kwargs):
    """One API call. Every strategy goes through here, so settings and accounting are identical."""
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            reasoning_effort="none",
            **kwargs
            )
    finally:
        usage["seconds"] += time.perf_counter() - t0
    usage["calls"] += 1
    if resp.usage:
        usage["input"] += resp.usage.prompt_tokens
        usage["output"] += resp.usage.completion_tokens
    return resp


def s1_direct(question: str) -> dict:
    usage = _new_usage()
    msgs = [
        {"role": "system", "content": SYSTEM_DIRECT + "\n\nDOCUMENTS:\n" + docs_text()},
        {"role": "user", "content": question},
    ]
    text = _chat(usage, messages=msgs).choices[0].message.content
    return {"text": text, "parsed": parse_answer(text), "usage": usage}


def s2_vote(question: str) -> dict:
    global _TEMP_OK
    usage = _new_usage()
    msgs = [
        {"role": "system", "content": SYSTEM_COT + "\n\nDOCUMENTS:\n" + docs_text()},
        {"role": "user", "content": question},
    ]
    samples = []
    for _ in range(K):
        if _TEMP_OK:
            try:
                resp = _chat(usage, messages=msgs, temperature=S2_TEMPERATURE)
            except Exception as e:
                if "temperature" not in str(e).lower():
                    raise
                _TEMP_OK = False
                resp = _chat(usage, messages=msgs)
        else:
            resp = _chat(usage, messages=msgs)
        samples.append(resp.choices[0].message.content)
    parsed = [parse_answer(s) for s in samples]
    votes = Counter(p for p in parsed if p is not None)
    winner = votes.most_common(1)[0][0] if votes else None
    return {"text": samples, "parsed": winner,
            "votes": [list(p) if p else None for p in parsed],
            "temperature_used": _TEMP_OK, "usage": usage}


def s3_tools(question: str, tools=None) -> dict:
    tools = tools or TOOLS
    usage = _new_usage()
    msgs = [
        {"role": "system", "content": SYSTEM_TOOLS},
        {"role": "user", "content": question},
    ]
    log = []
    for round_no in range(1, MAX_ROUNDS + 1):
        msg = _chat(usage, messages=msgs, tools=tools).choices[0].message
        if not msg.tool_calls:
            return {"text": msg.content, "parsed": parse_answer(msg.content),
                    "usage": usage, "rounds": round_no, "log": log}
        msgs.append(msg)
        for tc in msg.tool_calls:
            t0 = time.perf_counter()
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = None
            if not isinstance(args, dict):
                result = {"error": "arguments must be a valid JSON object"}
            else:
                try:
                    result = run_tool(tc.function.name, args)
                except Exception as e:  # a tool must never crash the loop
                    result = {"error": f"tool failed: {type(e).__name__}"}
            log.append({
                "round": round_no, "id": tc.id, "tool": tc.function.name,
                "arguments": tc.function.arguments, "result": result,
                "seconds": round(time.perf_counter() - t0, 4),
            })
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
    return {"text": None, "parsed": None, "usage": usage, "rounds": MAX_ROUNDS,
            "log": log, "unanswered": True}


def vague_tools():
    """C1: same tools, but lookup gets a one-line vague description."""
    t = copy.deepcopy(TOOLS)
    for tool in t:
        if tool["function"]["name"] == "lookup":
            tool["function"]["description"] = "Looks things up."
    return t


STRATEGIES = {"S1": s1_direct, "S2": s2_vote, "S3": s3_tools}
