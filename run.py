"""End-to-end run: collect -> analyse -> create.

Usage:
  python run.py --live      # pull fresh data (X API, Telegram, LinkedIn CSV export, re7.capital blog)
  python run.py             # use data/seed_posts.csv (snapshot collected 28 Oct 2026)
AI steps use Claude when ANTHROPIC_API_KEY is set, otherwise rule-based fallbacks.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import analyse
import collect
import create

ROOT = Path(__file__).parent
OUT = ROOT / "output"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--linkedin-csv", default=str(ROOT / "data/linkedin_export.csv"))
    args = ap.parse_args()
    use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))

    # 1. Collect
    if args.live:
        posts = []
        for handle in ("Re7Capital", "Re7Labs"):
            try:
                posts += collect.collect_x(handle)
            except Exception as e:
                print(f"[x] {handle}: {e}")
        if Path(args.linkedin_csv).exists():
            posts += collect.collect_linkedin_export(args.linkedin_csv)
        for ch in ("re7capital", "re7labs"):
            posts += collect.collect_telegram(ch)
        sources = collect.collect_blog()
    else:
        posts = collect.load(ROOT / "data/seed_posts.csv")
        sources = json.loads((ROOT / "data/seed_sources.json").read_text())
    collect.save(posts, OUT / "posts.csv")
    print(f"collected {len(posts)} posts")

    # 2. Analyse
    themes, summary = analyse.run(posts, use_llm)
    (OUT / "themes.json").write_text(json.dumps(themes, indent=1))
    (OUT / "insights.json").write_text(json.dumps(summary, indent=1))

    # 3. Create
    drafts = create.create_llm(summary, sources) if use_llm else create.create_template(summary, sources)
    (OUT / "drafts.json").write_text(json.dumps(drafts, indent=1, ensure_ascii=False))

    # Report
    lines = ["# Re7 social performance report", ""]
    for ch, b in summary.items():
        lines += [f"## {ch} ({b['posts']} posts)", "", "| theme | n | median engagements | median eng. rate |", "|---|---|---|---|"]
        lines += [f"| {r['theme']} | {r['n']} | {r['median_engagements']} | {r['median_engagement_rate'] or '-'} |" for r in b["by_theme"]]
        lines += ["", "| format | n | median engagements | median eng. rate |", "|---|---|---|---|"]
        lines += [f"| {r['format']} | {r['n']} | {r['median_engagements']} | {r['median_engagement_rate'] or '-'} |" for r in b["by_format"]]
        lines.append("")
    lines += ["## Drafts", ""] + [f"### {k}\n\n{v}\n" for k, v in drafts.items()]
    (OUT / "report.md").write_text("\n".join(lines))
    print(f"mode: {'Claude' if use_llm else 'offline fallback'}; report -> {OUT/'report.md'}")


if __name__ == "__main__":
    main()
