import argparse
import json
import statistics
from pathlib import Path

from strategies import STRATEGIES, s3_tools, vague_tools

ROOT = Path(__file__).parent
OUT = ROOT / "outputs"

# TODO: fill from the OpenAI price page for gpt-5.6-luna (USD per 1M tokens)
PRICE_IN_PER_M = 0.20
PRICE_OUT_PER_M = 1.20

def is_correct(parsed, q) -> bool:
    if parsed is None:
        return False
    name, number = parsed
    if str(q["answer"]).strip().lower() != name:
        return False
    tol = 10 ** (-int(q["decimals"]))
    return abs(number - round(float(q["value"]), int(q["decimals"]))) <= tol * 1.0001


def question_text(q: dict) -> str:
    """Return the question text. In questions.json the key is 'question'."""
    try:
        return q["question"]
    except KeyError:
        raise KeyError(f"question {q.get('id')} has no 'question' field")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("strategy", choices=STRATEGIES)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", nargs="*", help="only these question ids, e.g. Q-09")
    ap.add_argument("--vague", action="store_true", help="C1: S3 with a vague lookup description")
    args = ap.parse_args()

    questions = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))
    if isinstance(questions, dict):  # tolerate {"questions": [...]}
        questions = questions.get("questions", list(questions.values()))
    if args.ids:
        questions = [q for q in questions if q["id"] in args.ids]
    if args.limit:
        questions = questions[: args.limit]

    fn = STRATEGIES[args.strategy]
    if args.vague:
        if args.strategy != "S3":
            raise SystemExit("--vague only works with S3")
        fn = lambda text: s3_tools(text, vague_tools())
    results = []
    for q in questions:
        r = fn(question_text(q))  # NEVER pass q["answer"] or q["value"] to the model
        r["id"] = q["id"]
        r["correct"] = is_correct(r["parsed"], q)
        results.append(r)
        print(f"{q['id']}: {'OK ' if r['correct'] else 'BAD'} parsed={r['parsed']} "
              f"in={r['usage']['input']} out={r['usage']['output']} s={r['usage']['seconds']:.1f}")

    OUT.mkdir(exist_ok=True)
    tag = ('_vague' if args.vague else '') + ('_partial' if (args.limit or args.ids) else '')
    path = OUT / f"{args.strategy}_run{args.run}{tag}.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    n_ok = sum(r["correct"] for r in results)
    unanswered = sum(r["parsed"] is None for r in results)
    tin = sum(r["usage"]["input"] for r in results)
    tout = sum(r["usage"]["output"] for r in results)
    secs = [r["usage"]["seconds"] for r in results]
    cost = tin / 1e6 * PRICE_IN_PER_M + tout / 1e6 * PRICE_OUT_PER_M
    print("\n| Run | Strategy | Correct | Unanswered | Input tok | Output tok | Median s | Total s | Cost ($) |")
    print(f"| {args.run} | {args.strategy} | {n_ok}/{len(results)} | {unanswered} | {tin} | {tout} | "
          f"{statistics.median(secs):.1f} | {sum(secs):.1f} | {cost:.4f} |")


if __name__ == "__main__":
    main()