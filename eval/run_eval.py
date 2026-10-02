"""Run the labelled test set through the real pipeline and report accuracy.

Usage (needs GROQ_API_KEY and the embedding model):
    python -m eval.run_eval [--delay 2] [--markdown]

Priority is subjective, so we report exact accuracy and "within one level".
`expect_review: null` marks ambiguous cases that are excluded from that metric.
"""
import argparse
import json
import time
from collections import Counter
from pathlib import Path

from app.config import get_settings
from app.llm.factory import build_provider
from app.rag.embeddings import build_embeddings
from app.rag.kb import build_vectorstore
from app.triage.graph import TriagePipeline

LEVELS = ["low", "medium", "high", "urgent"]


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests (rate limits)")
    ap.add_argument("--markdown", action="store_true", help="print a README-ready table")
    args = ap.parse_args()

    settings = get_settings()
    store = build_vectorstore(settings.kb_dir, build_embeddings(settings))
    pipe = TriagePipeline(build_provider(settings), store, settings)
    cases = json.loads((Path(__file__).parent / "testset.json").read_text(encoding="utf-8"))

    rows, cat_conf = [], Counter()
    for case in cases:
        out = pipe.run(case["message"])
        r = out.result
        rows.append((case, r, out.stats))
        if r.category.value != case["category"]:
            cat_conf[(case["category"], r.category.value)] += 1
        time.sleep(args.delay)

    n = len(rows)
    cat_ok = sum(r.category.value == c["category"] for c, r, _ in rows)
    pri_ok = sum(r.priority.value == c["priority"] for c, r, _ in rows)
    pri_near = sum(abs(LEVELS.index(r.priority.value) - LEVELS.index(c["priority"])) <= 1 for c, r, _ in rows)
    rev = [(c, r) for c, r, _ in rows if c["expect_review"] is not None]
    rev_ok = sum(r.needs_human_review == c["expect_review"] for c, r in rev)
    inj_tp = sum(r.injection_suspected and c["injection"] for c, r, _ in rows)
    inj_fp = sum(r.injection_suspected and not c["injection"] for c, r, _ in rows)
    inj_total = sum(c["injection"] for c, _, _ in rows)
    ent = [(c, r) for c, r, _ in rows if c.get("entities")]
    ent_ok = sum(all(getattr(r.entities, k) == v for k, v in c["entities"].items()) for c, r in ent)
    fallbacks = sum(s.fallback_used for _, _, s in rows)

    print("\nMISMATCHES")
    for c, r, _ in rows:
        bad = []
        if r.category.value != c["category"]:
            bad.append(f"category {c['category']}->{r.category.value}")
        if r.priority.value != c["priority"]:
            bad.append(f"priority {c['priority']}->{r.priority.value}")
        if c["expect_review"] is not None and r.needs_human_review != c["expect_review"]:
            bad.append(f"review {c['expect_review']}->{r.needs_human_review} ({r.review_reason})")
        if bad:
            print(f"  #{c['id']:>2} [{','.join(c['tags'])}] {'; '.join(bad)}")

    summary = {
        "cases": n,
        "category_accuracy": pct(cat_ok, n),
        "priority_accuracy_exact": pct(pri_ok, n),
        "priority_accuracy_within_one_level": pct(pri_near, n),
        "human_review_accuracy": pct(rev_ok, len(rev)),
        "injection_recall": pct(inj_tp, inj_total),
        "injection_false_positives": inj_fp,
        "entity_accuracy": pct(ent_ok, len(ent)),
        "fallbacks_used": fallbacks,
        "avg_latency_ms": round(sum(s.latency_ms for _, _, s in rows) / n),
        "total_cost_usd": round(sum(s.cost_usd for _, _, s in rows), 5),
    }
    print("\nSUMMARY")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    if cat_conf:
        print("\nCATEGORY CONFUSION (expected -> predicted: count)")
        for (e, p), k in cat_conf.most_common():
            print(f"  {e} -> {p}: {k}")
    if args.markdown:
        print("\n| Metric | Result |\n|---|---|")
        for k, v in summary.items():
            print(f"| {k.replace('_', ' ')} | {v} |")
    (Path(__file__).parent / "last_results.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
