"""Pathways: find colleges you can get into and afford, careers that fit you, and aid you qualify for."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pathways import aid as aidmod
from pathways.careers import LETTERS, NAMES, PLAIN, QUIZ, career_vector, match_careers, profile_from_answers, top_letters
from pathways.colleges import FIT_ORDER, Student, income_bracket, match_colleges
from pathways.data import careers_are_sample, load_careers, load_colleges
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


if "saved" not in st.session_state:
    st.session_state.saved = {}

# ── Sidebar: the student's profile ───────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧭 Your profile")
    name = st.text_input("First name (optional)", placeholder="Taty")
    gpa = st.slider("Unweighted GPA", 1.5, 4.0, 3.3, 0.05)
    test = st.segmented_control("Test scores", ["None", "SAT", "ACT"], default="None")
    sat = st.slider("SAT total", 400, 1600, 1150, 10) if test == "SAT" else None
    act = st.slider("ACT composite", 1, 36, 24) if test == "ACT" else None
    major = st.text_input("Intended major", placeholder="computer science, nursing, business…")
    fams = cip_families_for(major)
    if major and not fams:
        st.caption("No match for that major yet. Try a broader word, like 'engineering' or 'health'.")
    elif fams:
        st.caption("Matching programs in: " + ", ".join(CIP_FAMILIES[f] for f in fams))

    with st.expander("🏫 School preferences", expanded=True):
        states = st.multiselect("States", STATES, default=["NY"])
        years = st.segmented_control("Program length", ["4-year", "2-year", "Any"], default="4-year")
        control = st.segmented_control("Type", ["Any", "Public", "Private"], default="Any")
        size = st.selectbox("Size", ["Any", "Small (under 5k)", "Medium (5k-15k)", "Large (15k+)"])
        c1, c2 = st.columns(2)
        hbcu = c1.checkbox("HBCU")
        womens = c2.checkbox("Women's")

    with st.expander("💸 Money", expanded=True):
        income = st.slider("Household income ($/yr)", 0, 200_000, 45_000, 1_000, format="$%d")
        household = st.number_input("People in household", 1, 12, 4)
        status = st.selectbox("Citizenship / status", ["Citizen or permanent resident", "DACA", "Undocumented", "Other"])
        ny = st.checkbox("New York resident", value=True)
        first_gen = st.checkbox("First in family to go to college")
        budget = st.slider("Max I can pay per year after aid", 0, 60_000, 60_000, 1_000, format="$%d",
                           help="Leave at the max to see everything.")

student = Student(gpa=gpa, sat=sat, act=act, states=states, size=size, control=control or "Any",
                  years=years or "4-year", hbcu_only=hbcu, womens_only=womens, major=major,
                  max_cost=None if budget >= 60_000 else budget)
aid = aidmod.screen(aidmod.AidInput(income=income, household=int(household), ny_resident=ny,
                                    status=status, first_gen=first_gen))
colleges = colleges_df()
all_matches = match_colleges(colleges, student, income=income, n=0)
picks = match_colleges(colleges, student, income=income, n=15)

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
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:18px">
    <div class="stat"><b>{len(all_matches):,}</b><span>colleges fit your filters</span></div>
    <div class="stat"><b>{(all_matches['fit'] == 'Safety').sum() if len(all_matches) else 0}</b><span>likely admits (Safety)</span></div>
    <div class="stat"><b>{money(aid.total)}</b><span>est. Pell + TAP per year</span></div>
    <div class="stat"><b>{code}</b><span>your interest code</span></div>
  </div>
</div>""", unsafe_allow_html=True)

tab_col, tab_car, tab_aid, tab_map, tab_list = st.tabs(
    ["🎓 Colleges", "🧭 Careers", "💸 Aid", "🗺️ Map", f"⭐ My list ({len(st.session_state.saved)})"])

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
        show = all_matches[all_matches["unitid"].isin(chosen_ids)] if chosen_ids else picks
        title = f"Selected on the chart ({len(show)})" if chosen_ids else "Your balanced list"
        fit_filter = st.segmented_control("Show", ["All", "Safety", "Match", "Reach"], default="All", key="fitf")
        if fit_filter and fit_filter != "All":
            show = show[show["fit"] == fit_filter]
        st.markdown(f"### {title}")

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
                    {badge}<span class="muted">{r['city']}, {r['state']}</span>
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
