"""'Beat the model': players pick a podium before each race and are scored on the result.

Scoring per race (max 40):
- 10 points for each driver in the exact podium position picked,
- 4 points for a picked driver who finishes on the podium in a different position,
- +10 bonus for a perfect podium.

The model plays too: its pick is the top three of its latest forecast made before the race
started (a genuine forecast, never a backfill).
"""

from __future__ import annotations

import hashlib
import re
import secrets

EXACT, ON_PODIUM, PERFECT_BONUS = 10, 4, 10
NICKNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{1,18}[A-Za-z0-9]$")
MODEL_NAME = "The Model"


def score_pick(pick: list[str], podium: list[str]) -> int:
    """Points for a podium pick [p1, p2, p3] given the actual podium [p1, p2, p3]."""
    pts = 0
    for i, driver in enumerate(pick):
        if i < len(podium) and podium[i] == driver:
            pts += EXACT
        elif driver in podium:
            pts += ON_PODIUM
    if pick == podium[:3]:
        pts += PERFECT_BONUS
    return pts


def new_token() -> tuple[str, str]:
    """A fresh player token and the hash stored for it."""
    token = secrets.token_urlsafe(24)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def valid_nickname(nickname: str) -> bool:
    return bool(NICKNAME_RE.match(nickname)) and nickname.lower() != MODEL_NAME.lower()
