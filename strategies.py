"""S1 direct, S2 think-and-vote (k=5), S3 tools. Same model, same answer format."""
import json
import re
import time
from collections import Counter

from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOLS, load_corpus, run_tool

load_dotenv()
client = OpenAI()  # reads OPENAI_API_KEY from the environment; never print it

MODEL = "gpt-5.6-luna"
K = 5                 # S2 samples
S2_TEMPERATURE = 1.0  # TODO: if the model rejects temperature, say so in SUBMISSION.md
MAX_ROUNDS = 8        # S3 round limit; TODO: justify (e.g. the most calls a question needs + margin)

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

_ANSWER_RE = re.compile(r"ANSWER:\s*(.+?)\s*\|\s*([-+]?[\d.,]+)", re.IGNORECASE)


def docs_text() -> str:
    return "\n\n".join(f"[{d['id']}] {d['title']}\n{d['text']}" for d in load_corpus().values())


def parse_answer(text):
    """Return (name, number) from the last ANSWER line, or None."""
    matches = _ANSWER_RE.findall(text or "")
    if not matches:
        return None
    name, num = matches[-1]
    try:
        return name.strip().lower(), float(num.replace(",", ""))
    except ValueError:
        return None


def _chat(usage, **kwargs):
    """One API call; adds its tokens and seconds to `usage`."""
    t0 = time.perf_counter()
    resp = client.chat.completions.create(model=MODEL, **kwargs)
    usage["seconds"] += time.perf_counter() - t0
    usage["input"] += resp.usage.prompt_tokens
    usage["output"] += resp.usage.completion_tokens
    usage["calls"] += 1
    return resp


def _new_usage():
    return {"input": 0, "output": 0, "seconds": 0.0, "calls": 0}


def s1_direct(question: str) -> dict:
    usage = _new_usage()
    msgs = [
        {"role": "system", "content": SYSTEM_DIRECT + "\n\nDOCUMENTS:\n" + docs_text()},
        {"role": "user", "content": question},
    ]
    text = _chat(usage, messages=msgs).choices[0].message.content
    return {"text": text, "parsed": parse_answer(text), "usage": usage}


def s2_vote(question: str) -> dict:
    usage = _new_usage()
    msgs = [
        {"role": "system", "content": SYSTEM_COT + "\n\nDOCUMENTS:\n" + docs_text()},
        {"role": "user", "content": question},
    ]
    samples = []
    for _ in range(K):
        try:
            resp = _chat(usage, messages=msgs, temperature=S2_TEMPERATURE)
        except Exception as e:  # some models reject temperature
            if "temperature" not in str(e).lower():
                raise
            resp = _chat(usage, messages=msgs)
        samples.append(resp.choices[0].message.content)
    parsed = [parse_answer(s) for s in samples]
    votes = Counter(p for p in parsed if p is not None)
    winner = votes.most_common(1)[0][0] if votes else None
    return {"text": samples, "parsed": winner, "votes": [list(p) if p else None for p in parsed], "usage": usage}


def s3_tools(question: str) -> dict:
    usage = _new_usage()
    msgs = [
        {"role": "system", "content": SYSTEM_TOOLS},
        {"role": "user", "content": question},
    ]
    log = []
    for round_no in range(1, MAX_ROUNDS + 1):
        msg = _chat(usage, messages=msgs, tools=TOOLS).choices[0].message
        if not msg.tool_calls:
            return {"text": msg.content, "parsed": parse_answer(msg.content),
                    "usage": usage, "rounds": round_no, "log": log}
        msgs.append(msg)  # unchanged, with its tool_calls
        for tc in msg.tool_calls:  # answer EVERY tool_call_id
            t0 = time.perf_counter()
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = None
            result = run_tool(tc.function.name, args)
            log.append({
                "round": round_no, "id": tc.id, "tool": tc.function.name,
                "arguments": tc.function.arguments, "result": result,
                "seconds": round(time.perf_counter() - t0, 4),
            })
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
    # hit the round limit: unanswered
    return {"text": None, "parsed": None, "usage": usage, "rounds": MAX_ROUNDS,
            "log": log, "unanswered": True}


STRATEGIES = {"S1": s1_direct, "S2": s2_vote, "S3": s3_tools}