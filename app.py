"""Pathways: find colleges you can get into and afford, careers that fit you, and aid you qualify for."""
from __future__ import annotations

import os
from urllib.parse import urlencode

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pathways import aid as aidmod
from pathways.advisor import SUGGESTED, Profile, ask
from pathways.careers import LETTERS, NAMES, PLAIN, QUIZ, career_vector, match_careers, profile_from_answers, top_letters
from pathways.colleges import FIT_ORDER, Student, income_bracket, match_colleges
from pathways.data import careers_are_sample, load_careers, load_colleges
from pathways.distance import zip_location
from pathways.majors import CIP_FAMILIES, cip_families_for
from pathways.report import build_pdf

st.set_page_config(page_title="Pathways", page_icon="🧭", layout="wide")

FIT_COLORS = {"Safety": "#00b894", "Match": "#0984e3", "Reach": "#e17055", "Unknown": "#95a5a6"}
STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
          "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
          "ND", "OH", "OK", "OR", "PA", "PR", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1250px;}
.hero {background: linear-gradient(120deg,#6c5ce7 0%,#0984e3 55%,#00b894 100%); border-radius: 22px;
       padding: 28px 32px; color: white; margin-bottom: 18px; box-shadow: 0 12px 30px rgba(108,92,231,.25);}
.hero h1 {color: white; margin: 0; font-size: 2.3rem; letter-spacing: -0.5px;}
.hero p {margin: 6px 0 0; opacity: .92; font-size: 1.05rem;}
.stat {background: rgba(255,255,255,.16); border-radius: 14px; padding: 12px 16px; backdrop-filter: blur(4px);}
.stat b {font-size: 1.6rem; display: block;} .stat span {font-size: .82rem; opacity: .9;}
.card {border: 1px solid rgba(128,128,128,.22); border-radius: 16px; padding: 16px 18px; margin-bottom: 12px;
       transition: transform .15s ease, box-shadow .15s ease; background: rgba(128,128,128,.04);}
.card:hover {transform: translateY(-2px); box-shadow: 0 10px 24px rgba(0,0,0,.08);}
.card h4 {margin: 0 0 2px; font-size: 1.05rem;} .muted {opacity: .7; font-size: .86rem;}
.pill {display:inline-block; padding: 2px 10px; border-radius: 999px; color: white; font-size: .75rem;
       font-weight: 700; letter-spacing: .3px; margin-right: 6px;}
.why {font-size: .85rem; margin-top: 8px; padding-left: 10px; border-left: 3px solid rgba(108,92,231,.5);}
.bar {height: 8px; border-radius: 99px; background: rgba(128,128,128,.18); overflow: hidden; margin: 6px 0;}
.bar > div {height: 100%; border-radius: 99px; background: linear-gradient(90deg,#6c5ce7,#00b894);}
.kpi {font-size: 1.35rem; font-weight: 700;}
.tool {display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .72rem; font-weight: 600;
       margin: 0 6px 6px 0; background: rgba(108,92,231,.14); color: #6c5ce7;}
.check {font-size: .8rem; margin-top: 4px;}
.hero {padding-bottom: 118px;}
.st-key-herostats {margin-top: -122px; padding: 0 32px 18px; position: relative; z-index: 2;}
.st-key-herostats button {background: rgba(255,255,255,.16) !important; border: 1px solid rgba(255,255,255,.28) !important;
       border-radius: 14px !important; color: white !important; min-height: 76px; justify-content: flex-start;
       text-align: left; transition: transform .15s ease, background .15s ease;}
.st-key-herostats button:hover {background: rgba(255,255,255,.28) !important; transform: translateY(-2px);}
.st-key-herostats button p {color: white !important; margin: 0; font-size: .82rem; text-align: left;}
.st-key-herostats button strong {font-size: 1.6rem; display: block; line-height: 1.2;}
.st-key-herostats button div {justify-content: flex-start;}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def colleges_df():
    return load_colleges()


@st.cache_data
def careers_df():
    return load_careers()


def money(v) -> str:
    return "—" if v is None or pd.isna(v) else f"${v:,.0f}"


def pct(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.0%}"


def api_key():
    try:
        return st.secrets.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY")


if "saved" not in st.session_state:
    st.session_state.saved = {}

# ── Shared links: restore a profile from the URL (once per session) ─────────
# Only school-search settings are shared. Income, status, and name never go in a link.
SHARE_KEYS = {"gpa": float, "major": str, "zip": str, "miles": str, "n": int, "years": str, "control": str,
              "states": lambda v: [x for x in v.split(",") if x]}
if "restored" not in st.session_state:
    st.session_state.restored = True
    for k, cast in SHARE_KEYS.items():
        if k in st.query_params:
            try:
                st.session_state[k] = cast(st.query_params[k])
            except ValueError:
                pass
    for k, v in {"states": ["NY"], "years": "4-year", "control": "Any", "fitf": "All", "gpa": 3.3, "n": 15}.items():
        st.session_state.setdefault(k, v)

DISTANCES = ["Anywhere in my states", "10 miles", "25 miles", "50 miles", "100 miles", "250 miles"]

# ── Sidebar: the student's profile ───────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧭 Your profile")
    name = st.text_input("First name (optional)", placeholder="Taty")
    gpa = st.slider("Unweighted GPA", 1.5, 4.0, step=0.05, key="gpa")
    test = st.segmented_control("Test scores", ["None", "SAT", "ACT"], default="None")
    sat = st.slider("SAT total", 400, 1600, 1150, 10) if test == "SAT" else None
    act = st.slider("ACT composite", 1, 36, 24) if test == "ACT" else None
    major = st.text_input("Intended major", placeholder="computer science, nursing, business…", key="major")
    fams = cip_families_for(major)
    if major and not fams:
        st.caption("No match for that major yet. Try a broader word, like 'engineering' or 'health'.")
    elif fams:
        st.caption("Matching programs in: " + ", ".join(CIP_FAMILIES[f] for f in fams))

    with st.expander("📍 Distance from home", expanded=True):
        c1, c2 = st.columns([1, 1.4])
        zip_code = c1.text_input("Home ZIP", placeholder="11201", max_chars=5, key="zip")
        how_far = c2.selectbox("Within", DISTANCES, key="miles")
        home = zip_location(zip_code)
        if zip_code and not home:
            st.caption("We don't recognize that ZIP code. Use 5 digits, like 11201.")
        elif home:
            st.caption(f"📍 {home[2]}" + ("" if how_far == DISTANCES[0] else
                       f" · showing schools within {how_far}, in any state"))

    n_show = st.slider("How many schools in my list", 5, 50, step=5, key="n",
                       help="Your list keeps a balance of Safety, Match, and Reach schools.")

    with st.expander("🏫 School preferences", expanded=True):
        states = st.multiselect("States", STATES, key="states",
                                disabled=bool(home) and how_far != DISTANCES[0],
                                help="Turned off while a distance is set: a radius can cross state lines.")
        years = st.segmented_control("Program length", ["4-year", "2-year", "Any"], key="years")
        control = st.segmented_control("Type", ["Any", "Public", "Private"], key="control")
        size = st.selectbox("Size", ["Any", "Small (under 5k)", "Medium (5k-15k)", "Large (15k+)"])
        c1, c2 = st.columns(2)
        hbcu = c1.checkbox("HBCUs only", help="Only Historically Black Colleges and Universities.")
        womens = c2.checkbox("Women's colleges only",
                             help="Only colleges that admit women only, like Barnard. Leave this off to see "
                                  "every school; all of them admit women.")

    with st.expander("💸 Money", expanded=True):
        income = st.slider("Household income ($/yr)", 0, 200_000, 45_000, 1_000, format="$%d")
        household = st.number_input("People in household", 1, 12, 4)
        status = st.selectbox("Citizenship / status", ["Citizen or permanent resident", "DACA", "Undocumented", "Other"])
        ny = st.checkbox("New York resident", value=True)
        first_gen = st.checkbox("First in family to go to college")
        budget = st.slider("Max I can pay per year after aid", 0, 60_000, 60_000, 1_000, format="$%d",
                           help="Leave at the max to see everything.")

    if not api_key():
        st.text_input("✨ Anthropic API key (for the AI advisor)", type="password", key="user_key",
                      help="Used for this session only, never stored.")

student = Student(gpa=gpa, sat=sat, act=act, states=states, size=size, control=control or "Any",
                  years=years or "4-year", hbcu_only=hbcu, womens_only=womens, major=major,
                  max_cost=None if budget >= 60_000 else budget,
                  home=home[:2] if home else None,
                  max_miles=None if how_far == DISTANCES[0] else float(how_far.split()[0]))
aid = aidmod.screen(aidmod.AidInput(income=income, household=int(household), ny_resident=ny,
                                    status=status, first_gen=first_gen))
colleges = colleges_df()
all_matches = match_colleges(colleges, student, income=income, n=0)
picks = match_colleges(colleges, student, income=income, n=n_show)

# ── Career quiz state (answered on the Careers tab) ──────────────────────────
answers = {q: st.session_state.get(f"quiz_{i}") for i, q in enumerate(QUIZ)}
answered = {q: a for q, a in answers.items() if a}
profile = profile_from_answers(answered)
careers = match_careers(careers_df(), profile, n=12) if answered else pd.DataFrame()

# ── Hero ─────────────────────────────────────────────────────────────────────
hello = f"Hey {name}, here's" if name else "Here's"
code = "".join(top_letters(profile, 3)) or "—"
st.markdown(f"""
<div class="hero">
  <h1>Pathways</h1>
  <p>{hello} where you can get in, what you'd really pay, and careers that fit you.</p>
</div>""", unsafe_allow_html=True)

TABS = ["✨ Ask the AI advisor", "🎓 Colleges", "🧭 Careers", "💸 Aid", "🗺️ Map", "⭐ My list"]


def go_to(tab: str, fit: str | None = None):
    st.session_state.nav = tab
    if fit:
        st.session_state.fitf = fit


n_safe = int((all_matches["fit"] == "Safety").sum()) if len(all_matches) else 0
with st.container(key="herostats"):
    c = st.columns(4)
    c[0].button(f"**{len(all_matches):,}**\n\ncolleges fit your filters →", on_click=go_to, args=(TABS[1], "All"),
                width="stretch", key="hs_all")
    c[1].button(f"**{n_safe}**\n\nlikely admits (Safety) →", on_click=go_to, args=(TABS[1], "Safety"),
                width="stretch", key="hs_safe")
    c[2].button(f"**{money(aid.total)}**\n\nest. Pell + TAP per year →", on_click=go_to, args=(TABS[3],),
                width="stretch", key="hs_aid")
    c[3].button(f"**{code}**\n\nyour interest code →", on_click=go_to, args=(TABS[2],),
                width="stretch", key="hs_code")

tab_ai, tab_col, tab_car, tab_aid, tab_map, tab_list = st.tabs(TABS, key="nav", on_change="rerun")

# ── AI advisor (Claude + the matching engines) ───────────────────────────────
KEY = api_key() or st.session_state.get("user_key") or None
TOOL_LABEL = {"search_colleges": "searched colleges", "college_details": "college data",
              "find_careers": "O*NET careers", "aid_estimate": "aid screener", "majors_for": "major lookup"}
with tab_ai:
    st.markdown("#### Ask anything about colleges, careers, or paying for school")
    st.caption("The advisor is Claude, but it doesn't answer from memory. It calls the same tested engines as the "
               "rest of Pathways, using your profile on the left, and a fact-checker confirms every dollar amount "
               "and percentage in its answer came from real data.")
    chat = st.session_state.setdefault("chat", [])       # (role, text, tools, (verified, unverified))
    st.session_state.setdefault("history", [])
    for role, text_, tools, check in chat:
        with st.chat_message(role, avatar="🧭" if role == "assistant" else "🎓"):
            if tools:
                st.markdown("".join(f'<span class="tool">🔧 {TOOL_LABEL.get(n, n)}</span>' for n, _ in tools),
                            unsafe_allow_html=True)
            st.markdown(text_.replace("$", "\\$"))
            if check:
                ok, bad = check
                if bad:
                    st.markdown(f'<div class="check">⚠️ <b>Double-check:</b> {", ".join(bad)} '
                                "didn't come from Pathways data.</div>", unsafe_allow_html=True)
                elif ok:
                    st.markdown(f'<div class="check">✅ <b>Fact-checked:</b> all {len(ok)} '
                                f'number{"s" if len(ok) != 1 else ""} match real data.</div>',
                                unsafe_allow_html=True)
    if not chat:
        cols = st.columns(3)
        for i, q in enumerate(SUGGESTED):
            if cols[i % 3].button(q, key=f"sq_{i}", width="stretch"):
                st.session_state.pending = q
                st.rerun()
    question = st.chat_input("Ask the advisor…", disabled=not KEY) or st.session_state.pop("pending", None)
    if not KEY:
        st.info("Add an Anthropic API key in the sidebar to chat. Everything else in Pathways works without one.")
    elif question:
        chat.append(("user", question, [], None))
        prof = Profile(student, income, int(household), status, ny, first_gen, profile if answered else {})
        with st.spinner("Checking the data…"):
            try:
                turn, st.session_state.history = ask(question, prof, colleges, careers_df(),
                                                     st.session_state.history, api_key=KEY)
                g = turn.grounding
                chat.append(("assistant", turn.answer, turn.tools_used,
                             ([c.text for c in g.verified], [c.text for c in g.unverified]) if g else None))
            except Exception as e:
                chat.append(("assistant", f"Sorry, I couldn't reach the AI: {e}", [], None))
        st.rerun()
    if chat and st.button("Start over", key="clear_chat"):
        st.session_state.chat, st.session_state.history = [], []
        st.rerun()

# ── Colleges ─────────────────────────────────────────────────────────────────
with tab_col:
    if all_matches.empty:
        st.warning("No colleges match these filters. Try adding states or widening your preferences.")
    else:
        left, right = st.columns([1.35, 1])
        with left:
            st.markdown("#### What you'd pay vs. how many students graduate")
            st.caption("Each bubble is a college that fits your filters. Up and left = more value. "
                       "Drag a box around bubbles to inspect them.")
            plot = all_matches.dropna(subset=["net_cost", "grad_rate"]).query("grad_rate > 0").copy()
            plot["Graduation rate"] = plot["grad_rate"] * 100
            fig = px.scatter(plot, x="net_cost", y="Graduation rate", color="fit", size="size", size_max=38,
                             color_discrete_map=FIT_COLORS, hover_name="name", custom_data=["unitid"],
                             category_orders={"fit": list(FIT_ORDER)},
                             hover_data={"net_cost": ":$,.0f", "Graduation rate": ":.0f", "size": ":,",
                                         "fit": False},
                             labels={"net_cost": f"Avg. net price for families earning {income_bracket(income).replace('_', '-').replace('k', 'k')}",
                                     "size": "Undergrads"})
            fig.update_layout(height=430, margin=dict(l=0, r=0, t=10, b=0), legend_title_text="",
                              legend=dict(orientation="h", y=1.08), xaxis_tickprefix="$", yaxis_ticksuffix="%",
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            fig.update_traces(marker=dict(line=dict(width=1, color="white"), opacity=.85))
            sel = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode=("box", "lasso", "points"),
                                  key="scatter")
        with right:
            st.markdown("#### Your list balance")
            mix = picks["fit"].value_counts().reindex(list(FIT_ORDER)).dropna()
            donut = go.Figure(go.Pie(labels=mix.index, values=mix.values, hole=.62,
                                     marker_colors=[FIT_COLORS[f] for f in mix.index], sort=False))
            donut.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0), showlegend=True,
                                annotations=[dict(text=f"<b>{len(picks)}</b><br>picks", showarrow=False, font_size=16)])
            st.plotly_chart(donut, width="stretch")
            st.markdown(f"""<div class="muted">Counselors suggest a mix: a few safeties you'd be happy at,
            several matches, and some reaches. Your top {len(picks)} picks below are balanced that way and
            ranked by program strength in your major, graduation rate, then price.</div>""", unsafe_allow_html=True)

        chosen_ids = [p["customdata"][0] for p in (sel.selection.points if sel and sel.selection else [])]
        fit_filter = st.session_state.get("fitf") or "All"
        if chosen_ids:
            show, title = all_matches[all_matches["unitid"].isin(chosen_ids)], f"Selected on the chart"
        elif fit_filter != "All":  # a single fit: show every matching school of that kind, not just the picks
            show, title = all_matches[all_matches["fit"] == fit_filter].head(n_show), f"Your {fit_filter} schools"
        else:
            show, title = picks, "Your balanced list"

        st.markdown(f"### {title} ({len(show)})")
        f1, f2 = st.columns([1.2, 1])
        f1.segmented_control("Show", ["All", "Safety", "Match", "Reach"], key="fitf")
        sorts = ["Best match", "Cheapest", "Highest graduation"] + (["Closest"] if home else [])
        order = f2.selectbox("Sort by", sorts, key="sortby")
        by = {"Cheapest": ("net_cost", True), "Highest graduation": ("grad_rate", False),
              "Closest": ("miles", True)}.get(order)
        if by:
            show = show.sort_values(by[0], ascending=by[1], na_position="last")

        # Take your matches with you: spreadsheet, PDF, or a link
        export = show[["name", "city", "state", "fit", "why", "net_cost", "grad_rate", "admit_rate",
                       "earnings_10y", "miles", "website"]].rename(columns={
            "name": "College", "city": "City", "state": "State", "fit": "Fit", "why": "Why",
            "net_cost": "Net price per year", "grad_rate": "Graduation rate", "admit_rate": "Admit rate",
            "earnings_10y": "Earnings after 10 years", "miles": "Miles from home", "website": "Website"})
        if not home:
            export = export.drop(columns="Miles from home")
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇️ Spreadsheet (CSV)", export.to_csv(index=False).encode(), "my_college_matches.csv",
                           "text/csv", width="stretch")
        d2.download_button("⬇️ PDF report", build_pdf(show, careers if not careers.empty else pd.DataFrame(
            columns=["title", "match", "preparation", "why"]), aid, name), "my_college_matches.pdf",
                           "application/pdf", width="stretch")
        with d3.popover("🔗 Share", width="stretch"):
            params = {"gpa": gpa, "n": n_show, "years": years or "4-year", "control": control or "Any"}
            if major:
                params["major"] = major
            if home and how_far != DISTANCES[0]:
                params |= {"zip": zip_code, "miles": how_far}
            else:
                params["states"] = ",".join(states)
            base = (st.context.url or "").split("?")[0]
            st.caption("Anyone with this link sees the same search. Your income, status, and name are not included.")
            st.code(f"{base}?{urlencode(params)}", language=None, wrap_lines=True)

        cols = st.columns(2)
        for i, (_, r) in enumerate(show.head(30).iterrows()):
            with cols[i % 2]:
                badge = f'<span class="pill" style="background:{FIT_COLORS[r["fit"]]}">{r["fit"].upper()}</span>'
                tags = " · ".join(t for t in [
                    "Public" if r["control"] == 1 else "Private", f"{r['size']:,} undergrads",
                    "HBCU" if r["hbcu"] else "", "Women's" if r["womens"] else ""] if t)
                strength = (f" · {r['major_share']:.0%} of degrees in your major"
                            if major and r.get("major_share", 0) > 0 else "")
                st.markdown(f"""<div class="card">
                    {badge}<span class="muted">{r['city']}, {r['state']}{f" · 📍 {r['miles']:.0f} mi" if pd.notna(r.get('miles')) else ""}</span>
                    <h4>{r['name']}</h4><div class="muted">{tags}{strength}</div>
                    <div style="display:flex;gap:26px;margin-top:10px">
                      <div><div class="kpi">{money(r['net_cost'])}</div><div class="muted">net price / yr</div></div>
                      <div><div class="kpi">{pct(r['grad_rate'])}</div><div class="muted">graduate</div></div>
                      <div><div class="kpi">{pct(r['admit_rate'])}</div><div class="muted">admitted</div></div>
                      <div><div class="kpi">{money(r['earnings_10y'])}</div><div class="muted">earnings, 10 yrs</div></div>
                    </div>
                    <div class="why">{r['why']}</div></div>""", unsafe_allow_html=True)
                saved = r["unitid"] in st.session_state.saved
                if st.button("✓ Saved" if saved else "☆ Save to my list", key=f"save_{r['unitid']}",
                             disabled=saved, width="stretch"):
                    st.session_state.saved[r["unitid"]] = r.to_dict()
                    st.rerun()

# ── Careers ──────────────────────────────────────────────────────────────────
with tab_car:
    if careers_are_sample():
        st.info("Showing a small sample of careers. The full O*NET career list loads after the "
                "data build runs. See the README.")
    st.markdown("#### Quick interest quiz")
    st.caption("Six questions. Pick what sounds most like you, not what sounds impressive. "
               f"{len(answered)}/6 answered.")
    st.progress(len(answered) / 6)
    for i, (q, opts) in enumerate(QUIZ.items()):
        st.pills(q, list(opts), key=f"quiz_{i}")
    r_col, txt_col = st.columns([1.3, 1])
    with r_col:
        st.markdown("#### Your interest shape")
        if not answered:
            st.markdown('<div class="card">Answer a question and your interest chart appears here, '
                        'built on the RIASEC model career counselors use.</div>', unsafe_allow_html=True)
        else:
            mx = max(profile.values()) or 1
            r_vals = [profile[L] / mx * 100 for L in LETTERS]
            radar = go.Figure()
            radar.add_trace(go.Scatterpolar(r=r_vals + r_vals[:1], theta=[NAMES[L] for L in LETTERS] + [NAMES["R"]],
                                            fill="toself", name="You", line_color="#6c5ce7"))
            pick = st.selectbox("Compare with a career", careers["title"].tolist())
            row = careers[careers["title"] == pick].iloc[0]
            cv = career_vector(row)
            cm = max(cv) or 1
            c_vals = [v / cm * 100 for v in cv]
            radar.add_trace(go.Scatterpolar(r=c_vals + c_vals[:1], theta=[NAMES[L] for L in LETTERS] + [NAMES["R"]],
                                            fill="toself", name=pick, line_color="#00b894", opacity=.6))
            radar.update_layout(height=380, margin=dict(l=30, r=30, t=20, b=20), legend=dict(orientation="h"),
                                polar=dict(radialaxis=dict(visible=False, range=[0, 100])),
                                paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(radar, width="stretch")
    with txt_col:
        if answered:
            mine = top_letters(profile, 3)
            st.markdown("#### What this means")
            st.markdown(f"Your interest code is **{''.join(mine)}**. You lean toward "
                        + ", ".join(f"**{PLAIN[L]}**" for L in mine) + ".")
            st.markdown("Each career below is scored by how closely its O*NET interest profile has the "
                        "same *shape* as yours (cosine similarity). 100% means the same shape.")

    if answered:
        st.markdown("### Careers that fit you")
        cc = st.columns(3)
        for i, (_, c) in enumerate(careers.iterrows()):
            with cc[i % 3]:
                st.markdown(f"""<div class="card"><h4>{c['title']}</h4>
                    <div class="bar"><div style="width:{c['match']}%"></div></div>
                    <b>{c['match']}% match</b> <span class="muted">· {c['preparation']}</span>
                    <div class="muted" style="margin-top:6px">{str(c['description'])[:150]}…</div>
                    <div class="why">{c['why']}</div>
                    <div style="margin-top:6px"><a href="{c['onet_url']}" target="_blank">Salary and details on O*NET ↗</a></div>
                    </div>""", unsafe_allow_html=True)

# ── Aid ──────────────────────────────────────────────────────────────────────
with tab_aid:
    a1, a2 = st.columns([1, 1.3])
    with a1:
        st.markdown("#### Grants you may get (estimates)")
        k1, k2, k3 = st.columns(3)
        k1.metric("Pell Grant", money(aid.pell))
        k2.metric("NY TAP", money(aid.tap))
        k3.metric("Total / yr", money(aid.total))
        flags = []
        if aid.dream_act:
            flags.append("🟢 NYS Dream Act")
        if aid.opportunity_programs:
            flags.append("🟢 HEOP / EOP / SEEK")
        if flags:
            st.markdown(" &nbsp; ".join(flags))
        for n in aid.notes:
            st.markdown(f"- {n}")
        st.caption("Estimates for planning. Your real award comes from the FAFSA or the Dream Act application.")
    with a2:
        st.markdown("#### What families like yours actually pay")
        if all_matches.empty:
            st.caption("Pick some filters to compare schools.")
        else:
            opts = all_matches.dropna(subset=["net_price_0_30k"])
            order = list(dict.fromkeys([n for n in picks["name"] if n in set(opts["name"])] + sorted(opts["name"])))
            school = st.selectbox("School", order)
            row = opts[opts["name"] == school].iloc[0]
            labels = {"0_30k": "$0-30k", "30_48k": "$30-48k", "48_75k": "$48-75k", "75_110k": "$75-110k",
                      "110k_plus": "$110k+"}
            data = pd.DataFrame({"Family income": list(labels.values()),
                                 "Net price": [row[f"net_price_{k}"] for k in labels]})
            mine = labels[income_bracket(income)]
            bars = px.bar(data, x="Family income", y="Net price", text_auto="$,.0f")
            bars.update_traces(marker_color=["#6c5ce7" if x == mine else "rgba(108,92,231,.3)"
                                             for x in data["Family income"]])
            sticker = row["sticker"]
            if pd.notna(sticker):
                bars.add_hline(y=sticker, line_dash="dot", annotation_text=f"Sticker price {money(sticker)}")
            bars.update_layout(height=340, margin=dict(l=0, r=0, t=20, b=0), yaxis_tickprefix="$",
                               plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(bars, width="stretch")
            st.caption("Average price after grants, from the U.S. College Scorecard. Your bracket is highlighted.")

# ── Map ──────────────────────────────────────────────────────────────────────
with tab_map:
    pts = all_matches.dropna(subset=["lat", "lon"])
    if pts.empty:
        st.caption("No mappable schools for these filters.")
    else:
        m = px.scatter_geo(pts, lat="lat", lon="lon", color="fit", color_discrete_map=FIT_COLORS,
                           hover_name="name", size="size", size_max=24, scope="usa",
                           hover_data={"net_cost": ":$,.0f", "lat": False, "lon": False, "size": ":,"},
                           category_orders={"fit": list(FIT_ORDER)})
        m.update_geos(fitbounds="locations" if states else False, showland=True, landcolor="#f4f3ff",
                      showlakes=True, lakecolor="#dfe6fd", showsubunits=True, subunitcolor="#c8c6e8",
                      bgcolor="rgba(0,0,0,0)")
        m.update_traces(marker=dict(line=dict(width=.6, color="white"), opacity=.85))
        m.update_layout(height=620, margin=dict(l=0, r=0, t=0, b=0), legend_title_text="",
                        legend=dict(orientation="h", y=1.02), paper_bgcolor="rgba(0,0,0,0)")
        st.caption("Every college that fits your filters. Hover for net price; click the legend to hide a group.")
        st.plotly_chart(m, width="stretch")

# ── My list ──────────────────────────────────────────────────────────────────
with tab_list:
    saved = pd.DataFrame(st.session_state.saved.values())
    if saved.empty:
        st.markdown('<div class="card">Save schools from the Colleges tab and they show up here, '
                    'ready to compare and download as a PDF.</div>', unsafe_allow_html=True)
    else:
        saved = saved.sort_values("fit", key=lambda c: c.map(FIT_ORDER))
        st.markdown("#### Compare side by side")
        comp = saved.set_index("name")[["fit", "net_cost", "grad_rate", "admit_rate", "earnings_10y", "size"]]
        comp.columns = ["Fit", "Net price / yr", "Graduation rate", "Admit rate", "Earnings after 10 yrs", "Undergrads"]
        st.dataframe(comp.style.format({"Net price / yr": "${:,.0f}", "Graduation rate": "{:.0%}",
                                        "Admit rate": "{:.0%}", "Earnings after 10 yrs": "${:,.0f}",
                                        "Undergrads": "{:,}"}, na_rep="—"), width="stretch")
        c1, c2 = st.columns(2)
        pdf = build_pdf(saved, careers if not careers.empty else pd.DataFrame(
            columns=["title", "match", "preparation", "why"]), aid, name)
        c1.download_button("⬇️ Download my plan (PDF)", pdf, "my_pathways_plan.pdf", "application/pdf",
                           width="stretch", type="primary")
        if c2.button("Clear list", width="stretch"):
            st.session_state.saved = {}
            st.rerun()

st.markdown("---")
st.caption("Built by Doussouba Diakite · College data: U.S. Department of Education College Scorecard (public "
           "domain) · Career data: O*NET Database by the U.S. Department of Labor, Employment and Training "
           "Administration (USDOL/ETA), used under the CC BY 4.0 license · Estimates only, not financial advice.")
