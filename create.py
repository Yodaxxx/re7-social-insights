"""Create: turn the insights into new X, LinkedIn and Telegram drafts from Re7's own content."""
from __future__ import annotations

import json

from analyse import _claude

CHANNEL_RULES = {
    "x": "X/Twitter: a native thread of 4-6 posts, first post is a hook with one number, no link in post 1, link in last post.",
    "linkedin": "LinkedIn: 120-200 words, institutional tone, one clear insight up front, 3 short bullets, link at the end.",
    "telegram": "Telegram: short announcement for an official channel, 60-100 words, key numbers, link.",
}


def create_llm(summary: dict, sources: list[dict]) -> dict[str, str]:
    prompt = (
        "You are a marketing analyst at Re7 Capital, a DeFi investment firm writing for institutional allocators.\n"
        f"Performance insights per channel (top themes/formats first): {json.dumps(summary)[:6000]}\n"
        f"Source content to repurpose: {json.dumps(sources, ensure_ascii=False)[:12000]}\n"
        "Write one draft per channel, leaning on the themes and formats that perform best on that channel.\n"
        f"Channel rules: {json.dumps(CHANNEL_RULES)}\n"
        "Use only facts present in the sources. No investment advice, no price predictions.\n"
        'Return only JSON: {"x": "...", "linkedin": "...", "telegram": "..."}'
    )
    raw = _claude(prompt, max_tokens=3000)
    return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])


def create_template(summary: dict, sources: list[dict]) -> dict[str, str]:
    """Offline fallback: fills channel templates with the source headline."""
    src = sources[0] if sources else {"title": "Re7's Weekly", "url": "https://re7.capital/blog", "text": ""}
    best = {ch: (b["by_theme"][0]["theme"] if b.get("by_theme") else "") for ch, b in summary.items()}
    return {
        "x": f"[thread, theme: {best.get('x')}] 1/ {src['title']}\n...\n5/ Full piece: {src['url']}",
        "linkedin": f"[theme: {best.get('linkedin')}] {src['title']}\n- point 1\n- point 2\n- point 3\nRead more: {src['url']}",
        "telegram": f"New from Re7: {src['title']} {src['url']}",
    }
