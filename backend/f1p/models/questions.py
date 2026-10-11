"""Answer custom questions about a race by counting outcomes across simulated races.

Marginal probabilities ("P(VER wins)") are in every snapshot, but questions about several
drivers at once ("does HAM finish ahead of LEC?", "do both Ferraris make the podium?") need
the joint outcome of each simulated race. Every question here is evaluated on the same set of
simulated finishing orders, so answers are mutually consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

QuestionKind = Literal[
    "top_k",  # driver finishes in the top k
    "position",  # driver finishes exactly in position k
    "ahead",  # driver finishes ahead of other
    "team_top_k",  # both of a team's cars finish in the top k (k=2: one-two, k=3: double podium)
    "team_wins",  # the winner drives for team
    "podium_exact",  # drivers[0..2] finish 1st, 2nd, 3rd in that order
    "dnf",  # driver does not finish
]


@dataclass
class Question:
    kind: QuestionKind
    driver: str | None = None
    other: str | None = None
    team: str | None = None
    k: int | None = None
    drivers: list[str] = field(default_factory=list)


class QuestionError(ValueError):
    """The question does not make sense for this race (unknown driver, bad k, ...)."""


@dataclass
class Field:
    """The simulated races and who is in them."""

    driver_ids: list[str]
    teams: dict[str, str]  # driver id -> team id
    finish: np.ndarray  # (n_sims, n) 0-based positions
    retired: np.ndarray  # (n_sims, n) bool

    def idx(self, driver: str | None) -> int:
        if driver not in self.driver_ids:
            raise QuestionError(f"{driver!r} is not in this race")
        return self.driver_ids.index(driver)


def _k(q: Question, n: int) -> int:
    if q.k is None or not 1 <= q.k <= n:
        raise QuestionError(f"k must be between 1 and {n}")
    return q.k


def outcomes(q: Question, f: Field) -> np.ndarray:
    """Boolean array: did the question come true in each simulated race?"""
    n = len(f.driver_ids)
    pos = f.finish  # 0-based
    if q.kind == "top_k":
        return pos[:, f.idx(q.driver)] < _k(q, n)
    if q.kind == "position":
        return pos[:, f.idx(q.driver)] == _k(q, n) - 1
    if q.kind == "ahead":
        a, b = f.idx(q.driver), f.idx(q.other)
        if a == b:
            raise QuestionError("pick two different drivers")
        return pos[:, a] < pos[:, b]
    if q.kind == "dnf":
        return f.retired[:, f.idx(q.driver)]
    if q.kind in ("team_top_k", "team_wins"):
        members = [i for i, d in enumerate(f.driver_ids) if f.teams.get(d) == q.team]
        if not members:
            raise QuestionError(f"no drivers from {q.team!r} in this race")
        if q.kind == "team_wins":
            return (pos[:, members] == 0).any(axis=1)
        if len(members) < 2:
            raise QuestionError(f"{q.team!r} has only one car in this race")
        return (pos[:, members] < _k(q, n)).all(axis=1)
    if q.kind == "podium_exact":
        if len(q.drivers) != 3 or len(set(q.drivers)) != 3:
            raise QuestionError("pick three different drivers for P1, P2 and P3")
        idx = [f.idx(d) for d in q.drivers]
        return (pos[:, idx[0]] == 0) & (pos[:, idx[1]] == 1) & (pos[:, idx[2]] == 2)
    raise QuestionError(f"unknown question kind {q.kind!r}")


def answer(q: Question, f: Field) -> float:
    return float(outcomes(q, f).mean())


def actual_field(
    driver_ids: list[str], teams: dict[str, str], position_order: dict[str, int], dnfs: set[str]
) -> Field:
    """The real race as a single 'simulation', to check whether a question came true."""
    order = np.array([[position_order.get(d, len(driver_ids)) - 1 for d in driver_ids]])
    retired = np.array([[d in dnfs for d in driver_ids]])
    return Field(driver_ids, teams, order, retired)
