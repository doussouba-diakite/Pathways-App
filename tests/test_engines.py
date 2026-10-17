from pathlib import Path
import pandas as pd
import pytest

from pathways import aid
from pathways.careers import QUIZ, cosine, match_careers, profile_from_answers
from pathways.colleges import MATCH, REACH, SAFETY, UNKNOWN, Student, classify, income_bracket, match_colleges
from pathways.data import load_careers
from pathways.majors import cip_families_for


def school(**kw):
    base = dict(unitid=1, name="Test U", city="X", state="NY", control=1, two_year=0, size=8000, hbcu=0,
                womens=0, admit_rate=0.5, sat_25=1100, sat_75=1300, act_25=22, act_75=28, tuition_in=7000,
                room_board=14000, grad_rate=0.6, earnings_10y=50000, lat=40.7, lon=-74.0,
                net_price_0_30k=5000, net_price_30_48k=8000, net_price_48_75k=12000,
                net_price_75_110k=18000, net_price_110k_plus=22000, pcip_11=0.1, pcip_51=0.0)
    base.update(kw)
    return pd.Series(base)


# ── College fit ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sat,expected", [(1350, SAFETY), (1300, SAFETY), (1200, MATCH), (1000, REACH)])
def test_sat_percentiles(sat, expected):
    fit, why = classify(Student(sat=sat), school())
    assert fit == expected
    assert str(sat) in why  # every label explains itself


def test_act_used_when_no_sat():
    assert classify(Student(act=30), school())[0] == SAFETY


def test_acceptance_rate_fallback_is_never_safety_when_very_selective():
    s = school(sat_25=None, sat_75=None, act_25=None, act_75=None, admit_rate=0.08)
    assert classify(Student(gpa=4.0), s)[0] == REACH


def test_community_college_is_safety():
    s = school(sat_25=None, sat_75=None, act_25=None, act_75=None, admit_rate=None, two_year=1)
    assert classify(Student(gpa=2.0), s)[0] == SAFETY


def test_no_data_is_unknown_not_a_guess():
    s = school(sat_25=None, sat_75=None, act_25=None, act_75=None, admit_rate=None)
    assert classify(Student(gpa=3.5), s)[0] == UNKNOWN


@pytest.mark.parametrize("income,label", [(0, "0_30k"), (30_000, "0_30k"), (45_000, "30_48k"),
                                          (100_000, "75_110k"), (300_000, "110k_plus")])
def test_income_brackets(income, label):
    assert income_bracket(income) == label


def test_match_uses_real_net_price_and_major_filter():
    df = pd.DataFrame([school(unitid=1, name="CS School", pcip_11=0.3),
                       school(unitid=2, name="No CS", pcip_11=0.0, pcip_51=0.5)])
    out = match_colleges(df, Student(sat=1200, major="computer science"), income=20_000, n=0)
    assert list(out["name"]) == ["CS School"]
    assert out.iloc[0]["net_cost"] == 5000


def test_for_profit_schools_are_excluded():
    df = pd.DataFrame([school(control=3)])
    assert match_colleges(df, Student(), n=0).empty


# ── Majors ───────────────────────────────────────────────────────────────────
def test_major_keywords():
    assert cip_families_for("Nursing") == ["51"]
    assert cip_families_for("computer engineering") == ["14", "11"]
    assert cip_families_for("") == []


# ── Careers ──────────────────────────────────────────────────────────────────
def test_cosine_basics():
    assert cosine([1, 0], [5, 0]) == pytest.approx(1.0)  # same shape, different size
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([0, 0], [1, 1]) == 0.0


def test_every_quiz_answer_scores_something():
    for q, opts in QUIZ.items():
        for choice in opts:
            assert sum(profile_from_answers({q: choice}).values()) > 0


def test_investigative_student_gets_investigative_careers():
    careers = load_careers()
    answers = {q: next(c for c, pts in opts.items() if "I" in pts and max(pts, key=pts.get) == "I")
               for q, opts in QUIZ.items()}
    top = match_careers(careers, profile_from_answers(answers), n=3)
    assert all(row["I"] >= 5 for _, row in top.iterrows())
    assert top["match"].between(0, 100).all()


# ── Aid ──────────────────────────────────────────────────────────────────────
def test_low_income_citizen_gets_max_pell_and_tap():
    r = aid.screen(aid.AidInput(income=8_000, household=3))
    assert r.pell == aid.PELL_MAX and r.tap == aid.TAP_MAX and r.opportunity_programs


def test_undocumented_student_gets_dream_act_not_pell():
    r = aid.screen(aid.AidInput(income=30_000, status="Undocumented"))
    assert r.pell == 0 and r.dream_act and r.tap > 0


def test_tap_cutoff():
    assert aid.estimate_tap(125_000) >= aid.TAP_MIN
    assert aid.estimate_tap(125_001) == 0


def test_opportunity_limit_grows_with_household():
    limits = [aid.opportunity_limit(n) for n in range(1, 11)]
    assert limits == sorted(limits)
    assert aid.opportunity_limit(10) == aid.OPP_LIMITS[8] + 2 * aid.OPP_EXTRA_PERSON


# ── Distance from home ───────────────────────────────────────────────────────
def test_zip_lookup_and_miles():
    from pathways.distance import miles, zip_location
    lat, lon, place = zip_location("11201")
    assert place == "Brooklyn, NY"
    # Brooklyn -> Albany is about 135 miles as the crow flies
    assert 125 < miles(lat, lon, [42.65], [-73.75])[0] < 145
    assert zip_location("abcde") is None and zip_location("00000") is None


def test_radius_and_states_work_together():
    from pathways.distance import zip_location
    colleges = pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "colleges.csv")
    home = zip_location("11201")[:2]
    anywhere = match_colleges(colleges, Student(gpa=3.3, states=[], home=home, max_miles=25), income=45_000, n=0)
    assert len(anywhere) and anywhere["miles"].max() <= 25
    assert "NJ" in set(anywhere["state"])  # no states picked: a radius from Brooklyn reaches New Jersey
    ny_only = match_colleges(colleges, Student(gpa=3.3, states=["NY"], home=home, max_miles=25), income=45_000, n=0)
    assert set(ny_only["state"]) == {"NY"} and len(ny_only) < len(anywhere)


def test_majors_tolerate_typos_and_ai_fallback_is_restricted():
    from types import SimpleNamespace as NS
    from pathways.majors import ai_families
    assert cip_families_for("anthropolopy") == ["45"] and cip_families_for("nursign") == ["51"]
    assert cip_families_for("basket weaving") == []
    fake = NS(messages=NS(create=lambda **kw: NS(content=[NS(type="tool_use", input={"families": ["50", "99"]})])))
    assert ai_families("basket weaving", client=fake) == ["50"]  # an invented code is dropped


@pytest.mark.parametrize("rate,gpa,expected", [
    (0.80, 3.3, SAFETY),   # e.g. City Tech: a 3.3 student is very likely admitted
    (0.58, 3.3, MATCH),    # e.g. Brooklyn College
    (0.58, 2.5, REACH),
    (0.47, 3.3, REACH),    # e.g. Baruch
    (0.47, 3.6, MATCH),
    (0.20, 4.0, REACH),
])
def test_no_test_score_tiers(rate, gpa, expected):
    s = school(sat_25=None, sat_75=None, act_25=None, act_75=None, admit_rate=rate)
    assert classify(Student(gpa=gpa), s)[0] == expected


def test_cuny_suny_rank_first_within_each_fit_group():
    colleges = pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "colleges.csv")
    s = Student(gpa=3.3, states=["NY"], years="Any", home_state="NY")
    df = match_colleges(colleges, s, income=45_000, n=15)
    for fit in ("Safety", "Match"):
        grp = df[df["fit"] == fit]
        if grp["home_public"].any():
            # once a private school appears in a group, no CUNY/SUNY comes after it
            assert grp["home_public"].tolist() == sorted(grp["home_public"].tolist(), reverse=True)
    assert set(df.loc[df["home_public"], "system"]) <= {"CUNY", "SUNY"}
    assert "United States Merchant Marine Academy" not in set(df.loc[df["home_public"], "name"])


def test_undecided_students_get_major_ideas_that_resolve():
    from pathways.majors import majors_for_interests
    ideas = majors_for_interests(["S", "I"])
    assert ideas[:2] == ["nursing", "biology"] and len(ideas) == len(set(ideas))
    assert all(cip_families_for(m) for m in ideas)  # every suggestion maps to real major families


def test_closed_colleges_are_not_shown():
    from pathways.data import DATA, load_colleges
    if not (DATA / "admissions.csv").exists():
        pytest.skip("admissions data not built")
    names = set(load_colleges()["name"])
    assert "Wells College" not in names and "University of the Arts" not in names  # both closed in 2024
    assert "Barnard College" in names
