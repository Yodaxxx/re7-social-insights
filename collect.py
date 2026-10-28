"""Collect: pull Re7's recent posts from X, LinkedIn and Telegram into one table.

Each collector returns rows with the same schema:
channel, account, post_id, date, format, text, url, impressions, engagements

- X: official API v2 (needs X_BEARER_TOKEN). Uses public_metrics.
- LinkedIn: the Posts API needs LinkedIn Marketing partner approval, so the
  default path reads the CSV that Page admins can export from
  LinkedIn Page analytics > Content (one click, no approval needed).
- Telegram: public channels expose a web preview at t.me/s/<channel>; we parse it
  (views, date, media type). No bot or API key needed.
- Website: re7.capital/blog, used as source material for repurposing.
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, asdict, fields
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (re7-social-insights)"}


@dataclass
class Post:
    channel: str
    account: str
    post_id: str
    date: str
    format: str
    text: str
    url: str
    impressions: int | None
    engagements: int

    @property
    def engagement_rate(self) -> float | None:
        if self.impressions:
            return self.engagements / self.impressions
        return None


# ---------------------------------------------------------------- X
def collect_x(handle: str, max_results: int = 50) -> list[Post]:
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        raise RuntimeError("X_BEARER_TOKEN not set")
    h = {"Authorization": f"Bearer {token}", **UA}
    uid = requests.get(f"https://api.x.com/2/users/by/username/{handle}", headers=h, timeout=30).json()["data"]["id"]
    r = requests.get(
        f"https://api.x.com/2/users/{uid}/tweets",
        headers=h,
        params={
            "max_results": max_results,
            "exclude": "retweets,replies",
            "tweet.fields": "created_at,public_metrics,attachments,entities",
            "expansions": "attachments.media_keys",
            "media.fields": "type",
        },
        timeout=30,
    ).json()
    media = {m["media_key"]: m["type"] for m in r.get("includes", {}).get("media", [])}
    out = []
    for t in r.get("data", []):
        m = t["public_metrics"]
        keys = t.get("attachments", {}).get("media_keys", [])
        kind = media.get(keys[0], "text") if keys else ("link" if t.get("entities", {}).get("urls") else "text")
        kind = {"photo": "image", "animated_gif": "video"}.get(kind, kind)
        out.append(Post("x", handle, t["id"], t["created_at"][:10], kind, t["text"],
                        f"https://x.com/{handle}/status/{t['id']}", m.get("impression_count"),
                        m["like_count"] + m["retweet_count"] + m["reply_count"] + m.get("quote_count", 0) + m.get("bookmark_count", 0)))
    return out


# ---------------------------------------------------------------- LinkedIn
def collect_linkedin_export(path: str, account: str = "Re7 Capital") -> list[Post]:
    """Read the 'Content' export from LinkedIn Page analytics (CSV, all posts)."""
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            g = lambda *k: next((row[x] for x in k if x in row and row[x] != ""), "")
            eng = sum(int(float(g(k) or 0)) for k in ("Likes", "Comments", "Reposts"))
            out.append(Post("linkedin", account, g("Post link"), g("Created date")[:10],
                            (g("Content Type") or "text").lower(), g("Post title"), g("Post link"),
                            int(float(g("Impressions") or 0)) or None, eng))
    return out


# ---------------------------------------------------------------- Telegram
def collect_telegram(channel: str) -> list[Post]:
    html = requests.get(f"https://t.me/s/{channel}", headers=UA, timeout=30).text
    return parse_telegram_html(html, channel)


def _num(s: str) -> int:
    s = s.strip().upper().replace(",", "")
    mult = 1000 if s.endswith("K") else 1_000_000 if s.endswith("M") else 1
    return int(float(s.rstrip("KM") or 0) * mult)


def parse_telegram_html(html: str, channel: str) -> list[Post]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for m in soup.select(".tgme_widget_message"):
        text_el = m.select_one(".tgme_widget_message_text")
        if not text_el:
            continue
        views = m.select_one(".tgme_widget_message_views")
        reactions = sum(_num(re.sub(r"[^\d.KM]", "", r.get_text())) for r in m.select(".tgme_reaction") if re.search(r"\d", r.get_text()))
        kind = ("video" if m.select_one(".tgme_widget_message_video_player") else
                "image" if m.select_one(".tgme_widget_message_photo_wrap") else
                "link" if m.select_one(".tgme_widget_message_link_preview") else "text")
        post = m.get("data-post", "")
        out.append(Post("telegram", channel, post, (m.select_one("time") or {}).get("datetime", "")[:10], kind,
                        text_el.get_text(" ", strip=True), f"https://t.me/{post}",
                        _num(views.get_text()) if views else None, reactions))
    return out


# ---------------------------------------------------------------- Website (source content)
def collect_blog(base: str = "https://re7.capital", limit: int = 5) -> list[dict]:
    soup = BeautifulSoup(requests.get(f"{base}/blog", headers=UA, timeout=30).text, "html.parser")
    links = []
    for a in soup.select('a[href*="/blog/"]'):
        href = a["href"] if a["href"].startswith("http") else base + a["href"]
        if href not in links:
            links.append(href)
    docs = []
    for url in links[:limit]:
        page = BeautifulSoup(requests.get(url, headers=UA, timeout=30).text, "html.parser")
        title = page.find("h1").get_text(strip=True) if page.find("h1") else url
        body = (page.find("article") or page.find("main") or page).get_text(" ", strip=True)
        docs.append({"title": title, "url": url, "text": body[:6000]})
    return docs


# ---------------------------------------------------------------- storage
def save(posts: list[Post], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, [x.name for x in fields(Post)])
        w.writeheader()
        for p in posts:
            w.writerow(asdict(p))


def load(path: str | Path) -> list[Post]:
    with open(path, newline="", encoding="utf-8") as f:
        return [Post(r["channel"], r["account"], r["post_id"], r["date"], r["format"], r["text"], r["url"],
                     int(r["impressions"]) if r["impressions"] else None, int(r["engagements"] or 0))
                for r in csv.DictReader(f)]
