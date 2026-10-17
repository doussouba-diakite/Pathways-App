"""The AI advisor: every tool on real data, the agent loop, and the fact-checker (fake Claude, no API key)."""
import json
from types import SimpleNamespace as NS

from pathways.advisor import TOOLS, Profile, ask, run_tool
from pathways.colleges import Student
from pathways.data import load_careers, load_colleges
from pathways.grounding import verify

C, K = load_colleges(), load_careers()
P = Profile(Student(gpa=3.3, states=["NY"]), income=45_000,
            interests={"R": .2, "I": .9, "A": .1, "S": .4, "E": .1, "C": .3})


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


def tool_use(name, args, id_="t1"):
    return NS(stop_reason="tool_use", content=[NS(type="tool_use", name=name, input=args, id=id_)])


def text(t):
    return NS(stop_reason="end_turn", content=[NS(type="text", text=t)])


def test_every_tool_runs_on_real_data():
    args = {"college_details": {"name": "Hunter"}, "majors_for": {"interest": "nursing"}}
    for t in TOOLS:
        out = run_tool(t["name"], args.get(t["name"], {}), P, C, K)
        assert out and '"error"' not in json.dumps(out, default=str)


def test_search_respects_overrides_and_profile():
    out = run_tool("search_colleges", {"states": ["NJ"], "fit": ["Match"], "sort_by": "cheapest", "limit": 4}, P, C, K)
    assert all(s["state"] == "NJ" and s["fit"] == "Match" for s in out["schools"])
    prices = [s["net_price_for_you"] for s in out["schools"] if s["net_price_for_you"] is not None]
    assert prices == sorted(prices)


def test_details_use_the_students_income_bracket():
    d = run_tool("college_details", {"name": "Binghamton"}, P, C, K)[0]
    assert d["your_income_bracket"] == "$30-48k"
    assert d["net_price_for_you"] == d["net_price_by_family_income"]["$30-48k"]


def test_unknown_college_is_an_error_not_a_guess():
    assert "error" in run_tool("college_details", {"name": "Hogwarts"}, P, C, K)


def test_careers_ranked_by_quiz_when_available():
    out = run_tool("find_careers", {"limit": 5}, P, C, K)
    assert out["ranked_by_your_interests"] and out["your_interest_code"].startswith("I")
    m = [c["match_percent"] for c in out["careers"]]
    assert m == sorted(m, reverse=True)


def test_loop_answers_and_fact_checks():
    d = run_tool("college_details", {"name": "Binghamton"}, P, C, K)[0]
    price = d["net_price_for_you"]
    client = FakeClient([tool_use("college_details", {"name": "Binghamton"}),
                         text(f"Binghamton costs families like yours about ${price:,.0f} a year. "
                              f"It's a reach, and graduates earn $999,999.")])
    turn, history = ask("Is Binghamton a reach?", P, C, K, client=client)
    assert turn.tools_used == [("college_details", {"name": "Binghamton"})] and len(history) == 4
    assert [c.text for c in turn.grounding.unverified] == ["$999,999"]
    assert len(turn.grounding.verified) == 1


def test_rounded_money_passes_but_wrong_money_does_not():
    src = ['{"net_price_for_you": 15281}']
    assert verify("about $15,300", src, money_rel=0.03).ok
    assert not verify("about $19,000", src, money_rel=0.03).ok


def test_bad_arguments_go_back_to_claude():
    client = FakeClient([tool_use("aid_estimate", {"income": "lots"}), text("What's your income?")])
    turn, _ = ask("aid?", P, C, K, client=client)
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_profile_never_goes_in_the_prompt():
    client = FakeClient([text("Hi!")])
    ask("hello", P, C, K, client=client)
    sent = json.dumps(client.calls[0], default=str)
    assert "45000" not in sent and "45,000" not in sent


def test_why_school_is_grounded_and_keeps_income_out():
    from pathways.advisor import why_school
    from pathways.colleges import match_colleges
    r = match_colleges(C, P.student, income=P.income, n=0)
    r = r[r["name"] == "CUNY Hunter College"].iloc[0]
    price = f"${r['net_cost']:,.0f}"
    client = FakeClient([text(f"Hunter is a Match, and families like yours pay about {price} a year. "
                              f"It costs $90,000. Ask about SEEK.")])
    answer, g = why_school(r, P, client=client)
    assert [c.text for c in g.unverified] == ["$90,000"]
    sent = json.dumps(client.calls[0], default=str)
    assert "45000" not in sent and "45,000" not in sent
