"""Analyse: categorise posts by theme with AI, then rank themes and formats per channel."""
from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict

from collect import Post

THEMES = {
    "weekly_market_commentary": "Re7's Weekly: market recap, macro, BTC price action, DeFi yields",
    "tradfi_interviews": "Bloomberg 'Crypto Minutes' interviews and podcasts with TradFi / institutional guests",
    "institutional_research": "Long-form research reports and frameworks (e.g. DeFi risk framework)",
    "events_speaking": "Conference and panel announcements featuring Re7 people",
    "vault_launch_yield": "Re7 Labs vault launches, partnerships and APY / yield updates",
    "hiring_company": "Hiring, company milestones, press features",
    "other": "Anything else (including non-Re7 or spam content)",
}

MODEL = os.environ.get("RE7_MODEL", "claude-sonnet-4-5")


def _claude(prompt: str, max_tokens: int = 2000) -> str:
    import anthropic  # imported lazily so the pipeline also runs without the SDK
    client = anthropic.Anthropic()
    msg = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                 messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text


def classify_llm(posts: list[Post]) -> dict[str, str]:
    items = [{"id": p.post_id, "channel": p.channel, "text": p.text[:500]} for p in posts]
    prompt = (
        "You label social posts from Re7 Capital / Re7 Labs (a DeFi investment firm) by theme.\n"
        f"Themes: {json.dumps(THEMES, indent=1)}\n"
        "Return only JSON: an object mapping each post id to exactly one theme key.\n"
        f"Posts: {json.dumps(items, ensure_ascii=False)}"
    )
    raw = _claude(prompt)
    return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])


KEYWORDS = [
    ("other", ["for sale", "buy username"]),
    ("weekly_market_commentary", ["weekly"]),
    ("institutional_research", ["report", "framework", "research"]),
    ("tradfi_interviews", ["bloomberg", "crypto minutes", "podcast", "conversation with"]),
    ("events_speaking", ["will be speaking", "summit", "panel", "conference"]),
    ("vault_launch_yield", ["vault", "apy", "lending", "yield"]),
    ("hiring_company", ["hiring", "years", "featured"]),
]


def classify_rules(posts: list[Post]) -> dict[str, str]:
    """Offline fallback so the pipeline runs end to end without an API key."""
    out = {}
    for p in posts:
        t = p.text.lower()
        out[p.post_id] = next((theme for theme, kws in KEYWORDS if any(k in t for k in kws)), "other")
    return out


def summarise(posts: list[Post], themes: dict[str, str]) -> dict:
    """Per channel: median engagements and median engagement rate by theme and by format."""
    res: dict = {}
    for ch in sorted({p.channel for p in posts}):
        cp = [p for p in posts if p.channel == ch]
        block = {"posts": len(cp)}
        for dim in ("theme", "format"):
            groups = defaultdict(list)
            for p in cp:
                groups[themes[p.post_id] if dim == "theme" else p.format].append(p)
            rows = []
            for k, ps in groups.items():
                rates = [p.engagement_rate for p in ps if p.engagement_rate is not None]
                rows.append({
                    dim: k,
                    "n": len(ps),
                    "median_engagements": statistics.median(p.engagements for p in ps),
                    "median_impressions": statistics.median([p.impressions for p in ps if p.impressions]) if any(p.impressions for p in ps) else None,
                    "median_engagement_rate": round(statistics.median(rates), 4) if rates else None,
                })
            rows.sort(key=lambda r: (r["median_engagements"]), reverse=True)
            block[f"by_{dim}"] = rows
        res[ch] = block
    return res


def run(posts: list[Post], use_llm: bool) -> tuple[dict[str, str], dict]:
    themes = classify_llm(posts) if use_llm else classify_rules(posts)
    return themes, summarise(posts, themes)
