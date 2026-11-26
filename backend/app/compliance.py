"""Meta ads compliance checker.

Flags risky claims, text-heavy images and patterns that commonly get
Facebook/Instagram ads rejected. Used by Adam (ads) and shown in the UI.
"""
from __future__ import annotations

import re
from typing import Any

# Absolute claims / banned-ish phrasing for ads
RISKY_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bguaranteed\b", "high", "'guaranteed' is an absolute claim — Meta often rejects it."),
    (r"\b100\s?%", "high", "100% claims need proof; usually flagged."),
    (r"\bfree\b", "medium", "'free' needs clear terms; add conditions or rephrase."),
    (r"\b(best|#[# ]?1|number one|top)\b", "medium", "Superlative/ranking claim without source."),
    (r"\b(cure|heal|miracle|instant results?)\b", "high", "Health/outcome claim — high rejection risk."),
    (r"\b(money[- ]back|no risk|risk[- ]free)\b", "medium", "Risk-free/money-back requires visible terms."),
    (r"\b(you are approved|guaranteed acceptance|no credit check)\b", "high",
     "Financial-services claim — strict Meta policy."),
    (r"\b(act now|limited time only|hurry)\b", "low", "Urgency wording can trigger quality filters."),
    (r"\b(diabetes|cancer|weight loss|lose \d+\s?kg)\b", "high", "Health condition claim — restricted."),
    (r"\b(must be \d{2,})\b", "low", "Age-restricted phrasing — check targeting compliance."),
]

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF\u200d\u20e3]+"
)


def check_text(text: str, *, context: str = "ad") -> list[dict]:
    """Return list of issues: {severity, message, snippet}."""
    issues: list[dict] = []
    if not text or not text.strip():
        return [{"severity": "high", "message": "Empty text.", "snippet": ""}]

    for pattern, severity, message in RISKY_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            issues.append({"severity": severity, "message": message,
                           "snippet": text[max(0, m.start() - 20):m.end() + 20].strip()})

    # emoji density
    emojis = EMOJI_RE.findall(text)
    if len(emojis) > 8:
        issues.append({"severity": "medium",
                       "message": f"Emoji-heavy ({len(emojis)} emoji) — can look spammy.",
                       "snippet": ""})

    # all caps words
    caps = [w for w in re.findall(r"\b[A-Z]{4,}\b", text) if w not in ("CTA", "FAQ", "UTM")]
    if caps:
        issues.append({"severity": "low",
                       "message": f"All-caps words ({', '.join(caps[:5])}) — reduce shouting.",
                       "snippet": ""})

    # long primary text
    if context == "ad" and len(text) > 175:
        issues.append({"severity": "low",
                       "message": f"Primary text is {len(text)} chars — above the ~125-char sweet spot.",
                       "snippet": ""})
    if context == "headline" and len(text) > 40:
        issues.append({"severity": "medium",
                       "message": f"Headline {len(text)} chars — Meta truncates at ~40.",
                       "snippet": ""})
    return issues


def check_image_spec(image_brief: dict | str, *, text_overlay_ratio: float | None = None) -> list[dict]:
    """Flag text-heavy image designs (a common rejection reason)."""
    issues: list[dict] = []
    blob = image_brief if isinstance(image_brief, str) else str(image_brief)
    ratio = text_overlay_ratio
    if ratio is None:
        m = re.search(r"(\d{1,3})\s?%\s*(?:text|overlay|typography)", blob, re.I)
        if m:
            ratio = float(m.group(1)) / 100.0
        elif re.search(r"lots of text|text-heavy|heavy text", blob, re.I):
            ratio = 0.5
        else:
            ratio = 0.1  # assume compliant when unspecified
    if ratio > 0.2:
        issues.append({"severity": "high",
                       "message": f"Image text overlay ~{ratio:.0%} of frame (>20%) — common Meta rejection.",
                       "snippet": ""})
    if re.search(r"before/after|before\s*(?:and|&)\s*after", blob, re.I):
        issues.append({"severity": "high",
                       "message": "Before/after imagery is restricted on Meta.",
                       "snippet": ""})
    if re.search(r"celebrity|lookalike of|in the style of [A-Z][a-z]+ [A-Z]", blob):
        issues.append({"severity": "medium",
                       "message": "Possible personality/brand misuse in creative.",
                       "snippet": ""})
    return issues


def check_campaign(campaign: dict) -> dict:
    """Run all checks over Adam's campaign package. Returns report."""
    issues: list[dict] = []
    for i, v in enumerate(campaign.get("variants", [])):
        prefix = f"Variant {v.get('label', i)}"
        for field in ("headline", "primary_text"):
            for iss in check_text(str(v.get(field, "")),
                                  context="headline" if field == "headline" else "ad"):
                issues.append({**iss, "where": f"{prefix}.{field}"})
        for iss in check_image_spec(v.get("image_brief", "")):
            issues.append({**iss, "where": f"{prefix}.image_brief"})

    budget = campaign.get("budget_plan", {})
    daily = str(budget.get("daily", ""))
    if re.search(r"\d", daily) and not re.search(r"tbd|client|confirm", daily, re.I):
        issues.append({"severity": "medium",
                       "message": "Budget amount present — must be client-confirmed before launch.",
                       "snippet": daily, "where": "budget"})

    for claim in campaign.get("claims", []) or []:
        for iss in check_text(str(claim)):
            issues.append({**iss, "where": "claims"})

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: severity_rank.get(x["severity"], 3))
    return {
        "passed": not any(i["severity"] == "high" for i in issues),
        "issues": issues,
        "counts": {
            "high": sum(1 for i in issues if i["severity"] == "high"),
            "medium": sum(1 for i in issues if i["severity"] == "medium"),
            "low": sum(1 for i in issues if i["severity"] == "low"),
        },
    }


def check_calendar(days: list[dict]) -> dict:
    issues: list[dict] = []
    for d in days:
        cap = str(d.get("caption", ""))
        for iss in check_text(cap, context="caption"):
            issues.append({**iss, "where": f"day {d.get('day')}"})
    return {"passed": not any(i["severity"] == "high" for i in issues), "issues": issues[:30]}
