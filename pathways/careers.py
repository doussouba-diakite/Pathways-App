"""Career matching with RIASEC interest profiles.

RIASEC (Holland codes) describes interests in six areas:
Realistic, Investigative, Artistic, Social, Enterprising, Conventional.
O*NET rates every occupation on these six from 1 to 7. We build the same
six-number profile for the student from a short quiz, then compare the two
with cosine similarity.
"""
from __future__ import annotations

import math

import pandas as pd

LETTERS = "RIASEC"
NAMES = {"R": "Realistic", "I": "Investigative", "A": "Artistic",
         "S": "Social", "E": "Enterprising", "C": "Conventional"}
PLAIN = {"R": "hands-on, building and fixing", "I": "investigating and solving problems",
         "A": "creating and expressing", "S": "helping and teaching people",
         "E": "leading and persuading", "C": "organizing and working with details"}

# Each answer adds points to one or two letters. Primary letter gets 2, secondary 1.
QUIZ = {
    "Which sounds most fun?": {
        "Fixing a bike or building furniture": {"R": 2},
        "Figuring out why an experiment failed": {"I": 2},
        "Designing a poster or making music": {"A": 2},
        "Tutoring a friend": {"S": 2},
        "Starting a small business": {"E": 2},
        "Organizing a messy spreadsheet": {"C": 2},
    },
    "Your favorite class?": {
        "Shop, robotics, or gym": {"R": 2},
        "Science or math": {"I": 2, "C": 1},
        "Art, music, or writing": {"A": 2},
        "History or social studies": {"S": 1, "I": 1},
        "Computer science": {"I": 2, "R": 1},
        "Economics or business": {"E": 2, "C": 1},
    },
    "In a group project, you usually...": {
        "Build the actual thing": {"R": 2},
        "Do the research": {"I": 2},
        "Make it look good": {"A": 2},
        "Keep everyone getting along": {"S": 2},
        "Take charge and present": {"E": 2},
        "Make the schedule and checklist": {"C": 2},
    },
    "Where would you rather work?": {
        "Outdoors or on my feet": {"R": 2},
        "In a lab": {"I": 2},
        "In a studio": {"A": 2},
        "In a school, clinic, or community center": {"S": 2},
        "In an office, running a team": {"E": 2},
        "At a desk with clear tasks": {"C": 2},
    },
    "Pick a superpower for work:": {
        "I can fix anything": {"R": 2},
        "I can solve any puzzle": {"I": 2},
        "I can imagine anything": {"A": 2},
        "I can understand anyone": {"S": 2},
        "I can convince anyone": {"E": 2},
        "I never miss a detail": {"C": 2},
    },
    "What would make you proudest?": {
        "Something I built with my hands": {"R": 2},
        "A discovery": {"I": 2},
        "Something original I made": {"A": 2},
        "Someone I helped": {"S": 2},
        "A company I grew": {"E": 2},
        "A system that runs perfectly": {"C": 2},
    },
}


def profile_from_answers(answers: dict[str, str]) -> dict[str, float]:
    """Add up quiz points into a six-letter RIASEC profile."""
    prof = {L: 0.0 for L in LETTERS}
    for question, choice in answers.items():
        for letter, pts in QUIZ.get(question, {}).get(choice, {}).items():
            prof[letter] += pts
    return prof


def cosine(a: list[float], b: list[float]) -> float:
    """1.0 = same shape of interests, 0.0 = nothing in common."""
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def career_vector(row: pd.Series) -> list[float]:
    # O*NET scores run 1-7. Subtract 1 so "no interest" counts as zero.
    return [max(0.0, float(row[L]) - 1) for L in LETTERS]


def top_letters(profile: dict[str, float], k: int = 2) -> list[str]:
    return [L for L, v in sorted(profile.items(), key=lambda kv: -kv[1]) if v > 0][:k]


def match_careers(careers: pd.DataFrame, profile: dict[str, float], n: int = 15) -> pd.DataFrame:
    """Score every career against the student and return the top n with a reason."""
    stu = [profile[L] for L in LETTERS]
    df = careers.copy()
    df["match"] = df.apply(lambda r: round(100 * cosine(stu, career_vector(r))), axis=1)
    df = df.sort_values("match", ascending=False).head(n)
    mine = top_letters(profile)

    def reason(r):
        theirs = [L for L in sorted(LETTERS, key=lambda L: -r[L])][:2]
        shared = [NAMES[L] for L in mine if L in theirs]
        if shared:
            return "You both score high on " + " and ".join(shared) + "."
        return "Similar overall interest pattern."

    df["why"] = df.apply(reason, axis=1)
    return df
