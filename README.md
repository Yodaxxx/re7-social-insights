# Re7 social insights — collect → analyse → create

End-to-end workflow that finds what performs on Re7's social channels (Re7 Capital and Re7 Labs) and turns those insights into new content.

## Run
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # AI steps (theme tagging, drafting) use Claude
export X_BEARER_TOKEN=...           # X API v2, for live collection
python run.py --live --linkedin-csv data/linkedin_export.csv
python run.py                        # replay on the 28 Oct 2026 snapshot in data/
```
Without an Anthropic key the pipeline still runs end to end with rule-based fallbacks.

## Steps
1. **Collect** (`collect.py`) — X API v2 (public_metrics), LinkedIn Page analytics CSV export (the LinkedIn Posts API needs Marketing partner approval), Telegram public web preview (t.me/s/<channel>), re7.capital/blog for source content. Everything lands in one table: `output/posts.csv`.
2. **Analyse** (`analyse.py`) — Claude assigns each post one theme; the script ranks themes and formats per channel by median engagements and engagement rate.
3. **Create** (`create.py`) — Claude writes one draft per channel from Re7's latest Weekly and research, steered by the best-performing themes and formats, with channel rules and a facts-only constraint.

Outputs: `posts.csv`, `themes.json`, `insights.json`, `drafts.json`, `report.md` in `output/`.

## Scheduling
Run weekly (e.g. Monday after The Weekly is published) with cron or GitHub Actions; drafts go to the team for review, never auto-posted.
