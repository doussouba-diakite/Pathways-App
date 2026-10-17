"""The Pathways AI advisor: Claude + the matching engines + a loop.

A student asks things like "Which CUNY schools are cheapest for nursing?" or
"Is Binghamton a reach for me?". Claude doesn't answer from memory, which would
mean made-up acceptance rates and prices. It calls the same tested Python engines
the rest of the app uses (college fit, net price by income, career matching, aid
screening), then explains the results in plain words.

    question ─► Claude ─► tool_use ─► Python engine ─► tool_result ─► Claude ─► … ─► answer
                                                                             └─► fact-check every $, %, date

The student's sidebar profile is passed to the tools, not pasted into the prompt,
so Claude can only see the results the tools return.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, replace

import pandas as pd

from . import aid as aidmod
from .careers import LETTERS, NAMES, match_careers, top_letters
from .colleges import Student, classify, income_bracket, match_colleges
from .grounding import Grounding, today_sources, verify
from .majors import CIP_FAMILIES, cip_families_for

MODEL = os.environ.get("PATHWAYS_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 6

SYSTEM = """You are the Pathways college and career advisor. Many of the students you help are the first in their
family to go to college, come from low-income families, or are immigrants. Talk to them like a great school counselor:
warm, direct, specific, encouraging, and honest.

Rules:
- Get every fact (schools, acceptance rates, prices, graduation rates, earnings, aid amounts, careers) ONLY from your
  tools. Never state a number from memory. If the tools can't answer, say so and suggest where to look.
- The tools already know the student's profile (GPA, test scores, states, income, household, status). Use them first.
- Safety / Match / Reach are estimates from public data, never promises. Say so when it matters.
- Net price is the average that families in the student's income bracket actually paid after grants; their real
  price comes from each school's aid offer and net price calculator.
- Name real schools and careers from the tool results. Keep answers short: a few sentences or a short list.
- Never ask for or comment on immigration documents, Social Security numbers, or other private details. If the student
  is DACA or undocumented, point them to the NYS Dream Act and school-specific aid, without judgment.
- End with one concrete next step when it helps (a deadline, a form, a question to ask a school).
"""

TOOLS = [
    {"name": "search_colleges",
     "description": "Search colleges for this student, using their profile (GPA, scores, states, income) plus any "
                    "overrides. Returns schools with fit (Safety/Match/Reach) and why, net price for the student's "
                    "income, graduation rate, median earnings 10 years after entry, acceptance rate, and the share "
                    "of degrees in the requested major.",
     "input_schema": {"type": "object", "properties": {
         "states": {"type": "array", "items": {"type": "string"}, "description": "2-letter codes; omit = profile"},
         "major": {"type": "string", "description": "e.g. nursing, computer science"},
         "fit": {"type": "array", "items": {"type": "string", "enum": ["Safety", "Match", "Reach"]}},
         "max_net_price": {"type": "number", "description": "Max yearly price after grants"},
         "control": {"type": "string", "enum": ["Any", "Public", "Private"]},
         "years": {"type": "string", "enum": ["4-year", "2-year", "Any"]},
         "sort_by": {"type": "string", "enum": ["best_match", "cheapest", "graduation_rate", "earnings", "closest"]},
         "limit": {"type": "integer", "description": "1-10, default 6"}}}},
    {"name": "college_details",
     "description": "Everything known about one college by name (partial names work, e.g. 'Hunter' or "
                    "'Binghamton'): this student's fit and why, net price at every income level, costs, "
                    "graduation rate, earnings, test score ranges, and its biggest majors.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "find_careers",
     "description": "Careers from O*NET. If the student took the interest quiz, results are ranked by how well they "
                    "match the student's interests. Optional keyword filters titles and descriptions.",
     "input_schema": {"type": "object", "properties": {
         "keyword": {"type": "string", "description": "e.g. 'health', 'computer', 'teach'"},
         "limit": {"type": "integer", "description": "1-10, default 6"}}}},
    {"name": "aid_estimate",
     "description": "Estimated Pell Grant and NY TAP, NYS Dream Act eligibility, and opportunity programs "
                    "(HEOP/EOP/SEEK). Uses the student's profile unless you pass different values to compare.",
     "input_schema": {"type": "object", "properties": {
         "income": {"type": "number"}, "household": {"type": "integer"}}}},
    {"name": "majors_for",
     "description": "Which federal major families (CIP) match an interest, and how many colleges in the student's "
                    "states award degrees in them.",
     "input_schema": {"type": "object", "properties": {"interest": {"type": "string"}}, "required": ["interest"]}},
]

FIELDS = ["name", "city", "state", "miles", "fit", "why", "net_price_for_you", "sticker_price", "grad_rate",
          "earnings_10y", "admit_rate"]


@dataclass
class Profile:
    """What the student entered in the sidebar."""
    student: Student
    income: float
    household: int = 4
    status: str = "Citizen or permanent resident"
    ny_resident: bool = True
    first_gen: bool = False
    interests: dict = field(default_factory=dict)   # RIASEC profile from the quiz, may be empty


def clean(v):
    """JSON-safe values: NaN -> None, numpy -> python, rates rounded."""
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):
        v = v.item()
        return None if isinstance(v, float) and math.isnan(v) else v
    return v


def _college_rows(df: pd.DataFrame, cols=FIELDS) -> list[dict]:
    df = df.rename(columns={"net_cost": "net_price_for_you", "sticker": "sticker_price"})
    out = []
    for _, r in df.iterrows():
        d = {c: clean(r.get(c)) for c in cols}
        if d.get("miles") is None:
            d.pop("miles", None)
        else:
            d["miles_from_home"] = d.pop("miles")
        for k in ("net_price_for_you", "sticker_price", "earnings_10y"):
            if d.get(k) is not None:
                d[k] = round(d[k])
        for k in ("grad_rate", "admit_rate"):
            if d.get(k) is not None:
                d[k] = f"{d[k]:.0%}"
        if "major_share" in r and r["major_share"]:
            d["share_of_degrees_in_major"] = f"{r['major_share']:.0%}"
        out.append(d)
    return out


def run_tool(name: str, args: dict, p: Profile, colleges: pd.DataFrame, careers: pd.DataFrame):
    """Execute one tool against the real engines. Every fact the advisor states comes from here."""
    if name == "search_colleges":
        s = p.student
        over = {k: args[k] for k in ("states", "major", "control", "years") if args.get(k)}
        if args.get("max_net_price"):
            over["max_cost"] = float(args["max_net_price"])
        df = match_colleges(colleges, replace(s, **over), income=p.income, n=0)
        if args.get("fit"):
            df = df[df["fit"].isin(args["fit"])]
        sort = {"cheapest": ("net_cost", True), "graduation_rate": ("grad_rate", False),
                "earnings": ("earnings_10y", False), "closest": ("miles", True)}.get(args.get("sort_by", ""))
        if sort:
            df = df.sort_values(sort[0], ascending=sort[1], na_position="last")
        n = max(1, min(10, int(args.get("limit") or 6)))
        return {"total_matching": len(df), "searched_states": over.get("states", s.states) or "anywhere",
                "schools": _college_rows(df.head(n))}

    if name == "college_details":
        q = args["name"].strip().lower()
        hits = colleges[colleges["name"].str.lower().str.contains(q, regex=False, na=False)]
        if hits.empty:
            return {"error": f"No college named like '{args['name']}' in the College Scorecard data."}
        out = []
        for _, r in hits.head(3).iterrows():
            fit, why = classify(p.student, r)
            majors = sorted(((CIP_FAMILIES[c[5:]], r[c]) for c in colleges.columns
                             if c.startswith("pcip_") and c[5:] in CIP_FAMILIES and pd.notna(r[c]) and r[c] > 0),
                            key=lambda x: -x[1])[:5]
            brackets = {"$0-30k": "net_price_0_30k", "$30-48k": "net_price_30_48k", "$48-75k": "net_price_48_75k",
                        "$75-110k": "net_price_75_110k", "$110k+": "net_price_110k_plus"}
            out.append({
                "name": r["name"], "city": r["city"], "state": r["state"],
                "type": {1: "Public", 2: "Private nonprofit"}.get(int(r["control"]), "For-profit"),
                "two_year": bool(r["two_year"]), "undergrads": clean(r["size"]), "website": clean(r["website"]),
                "fit_for_you": fit, "why": why,
                "your_income_bracket": {"0_30k": "$0-30k", "30_48k": "$30-48k", "48_75k": "$48-75k",
                                        "75_110k": "$75-110k", "110k_plus": "$110k+"}[income_bracket(p.income)],
                "net_price_for_you": clean(r.get(f"net_price_{income_bracket(p.income)}")),
                "net_price_by_family_income": {k: clean(r.get(v)) for k, v in brackets.items()},
                "in_state_tuition": clean(r["tuition_in"]), "out_of_state_tuition": clean(r["tuition_out"]),
                "room_and_board": clean(r["room_board"]),
                "admit_rate": None if pd.isna(r["admit_rate"]) else f"{r['admit_rate']:.0%}",
                "sat_middle_50": None if pd.isna(r["sat_25"]) else f"{int(r['sat_25'])}-{int(r['sat_75'])}",
                "act_middle_50": None if pd.isna(r["act_25"]) else f"{int(r['act_25'])}-{int(r['act_75'])}",
                "grad_rate": None if pd.isna(r["grad_rate"]) else f"{r['grad_rate']:.0%}",
                "median_earnings_10y": clean(r["earnings_10y"]),
                "biggest_majors": [f"{m} ({v:.0%})" for m, v in majors]})
        return out

    if name == "find_careers":
        df = careers
        kw = (args.get("keyword") or "").strip().lower()
        if kw:
            df = df[df["title"].str.lower().str.contains(kw, regex=False)
                    | df["description"].str.lower().str.contains(kw, regex=False)]
        n = max(1, min(10, int(args.get("limit") or 6)))
        ranked = bool(p.interests) and any(p.interests.values())
        df = match_careers(df, p.interests, n=n) if ranked and len(df) else df.head(n)
        return {"ranked_by_your_interests": ranked,
                "your_interest_code": "".join(top_letters(p.interests, 3)) if ranked else None,
                "careers": [{"title": r["title"],
                             "match_percent": clean(r["match"]) if ranked else None,
                             "top_interests": [NAMES[L] for L in sorted(LETTERS, key=lambda L: -r[L])[:2]],
                             "preparation": r["preparation"], "what_they_do": r["description"][:220],
                             "onet_url": r["onet_url"]} for _, r in df.iterrows()]}

    if name == "aid_estimate":
        res = aidmod.screen(aidmod.AidInput(income=float(args.get("income", p.income)),
                                            household=int(args.get("household", p.household)),
                                            ny_resident=p.ny_resident, status=p.status, first_gen=p.first_gen))
        return {"pell_grant": res.pell, "ny_tap": res.tap, "total_per_year": res.total,
                "nys_dream_act": res.dream_act, "opportunity_programs": res.opportunity_programs,
                "notes": res.notes, "caveat": "Estimates. The FAFSA or Dream Act application gives the real amount."}

    if name == "majors_for":
        fams = cip_families_for(args["interest"])
        if not fams:
            return {"error": "No match. Try a broader word like 'engineering', 'health', or 'business'."}
        n = len(match_colleges(colleges, replace(p.student, major=args["interest"]), income=p.income, n=0))
        return {"major_families": [CIP_FAMILIES[f] for f in fams], "colleges_in_your_states_offering_it": n}

    return {"error": f"Unknown tool {name}"}


@dataclass
class Turn:
    answer: str
    tools_used: list[tuple[str, dict]] = field(default_factory=list)
    grounding: Grounding | None = None


def ask(question: str, p: Profile, colleges: pd.DataFrame, careers: pd.DataFrame, history: list | None = None,
        client=None, api_key: str | None = None) -> tuple[Turn, list]:
    """Run the agent loop for one question. Returns the answer and the updated message history."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    messages = list(history or []) + [{"role": "user", "content": question}]
    used, evidence = [], [question] + today_sources()
    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=MODEL, max_tokens=1500, system=SYSTEM, tools=TOOLS,
                                      messages=list(messages))
        messages.append({"role": "assistant", "content": resp.content})
        calls = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not calls:
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            return Turn(text, used, verify(text, evidence, money_rel=0.03)), messages
        results = []
        for c in calls:
            used.append((c.name, dict(c.input)))
            try:
                out = json.dumps(run_tool(c.name, dict(c.input), p, colleges, careers), default=str)
                evidence.append(out)
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": out})
            except Exception as e:  # bad arguments go back to Claude instead of crashing the app
                results.append({"type": "tool_result", "tool_use_id": c.id, "is_error": True, "content": str(e)})
        messages.append({"role": "user", "content": results})
    return Turn("I couldn't finish that in a few steps. Try a narrower question.", used, Grounding()), messages


SUGGESTED = [
    "Which of my schools are the best value for my family's income?",
    "Is Binghamton a reach for me? What would help?",
    "Find me cheap nursing programs in New York.",
    "What careers fit my quiz results, and what should I major in?",
    "How much aid could I get, and what forms do I need?",
    "Compare Hunter College and Stony Brook for computer science.",
]
