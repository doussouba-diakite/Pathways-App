# Pathways 🧭

**College, career, and financial aid matching for first-generation, low-income, and immigrant students.**

Most college search tools assume you have a counselor. A lot of students don't. Pathways answers three questions in one place, using only public federal data:

1. **Where can I get in?** Every college is labeled Safety, Match, or Reach, with a one-line reason.
2. **What would I actually pay?** Real average net price for families at *your* income, not the sticker price.
3. **What careers fit me?** A six-question interest quiz matched against U.S. Department of Labor career profiles.

![Colleges tab](docs/colleges.png)

| Careers | Aid |
| --- | --- |
| ![Careers](docs/careers.png) | ![Aid](docs/aid.png) |

## How the matching works

### Colleges: filter → classify → rank → balance
1. **Filter** ~3,100 public and nonprofit colleges by state, size, type, 2- or 4-year, HBCU, women's colleges, budget, and major. Majors match on the share of degrees each school awards in that field (federal CIP codes). For-profit schools are excluded.
2. **Classify** each school with the strongest evidence available:
   - SAT or ACT vs. the school's 25th and 75th percentiles (at or above 75th = Safety, inside the middle 50% = Match, below = Reach)
   - No scores? Acceptance rate plus GPA, deliberately conservative
   - No data at all? **Unknown**, never a guess
   Every label comes with a plain-English reason, so a student or counselor can check it.
3. **Rank** within each group by program strength in the student's major, then graduation rate, then net price.
4. **Balance** the list at about 25% Safety, 45% Match, 30% Reach.

### Careers: RIASEC + cosine similarity
The quiz builds a six-number interest profile (Realistic, Investigative, Artistic, Social, Enterprising, Conventional). O*NET rates every occupation on the same six scales. Pathways compares the two with **cosine similarity**, which measures whether two profiles have the same *shape* regardless of size. 100% = same shape.

### Aid: transparent rules
Pell, NY TAP, the NYS Dream Act, and HEOP/EOP/SEEK eligibility are published rules, so they're written as rules, not a model. Each threshold is cited in [`pathways/aid.py`](pathways/aid.py) with the date it was checked.

## Fairness check
Admissions labels should depend only on academics. [`scripts/fairness_audit.py`](scripts/fairness_audit.py) holds GPA and scores fixed, changes only family income, and compares labels across all ~2,000 matching schools:

```
GPA 3.4, SAT 1150 | income $15k -> $150k | labels that moved: 0 | schools checked: 2084
Result: PASS: income never changes admissions labels.
```

Price and aid *should* change with income, and they do. The audit also shows that undocumented and DACA students are routed to the NYS Dream Act instead of being silently dropped.

## Project structure
```
app.py                    Streamlit interface (5 tabs, interactive Plotly charts)
pathways/
  colleges.py             filter, classify, rank, balance
  careers.py              quiz, RIASEC profile, cosine similarity
  aid.py                  Pell, TAP, Dream Act, opportunity programs
  majors.py               typed major -> CIP families
  report.py               PDF export (ReportLab)
scripts/
  build_colleges.py       builds data/colleges.csv from College Scorecard
  build_careers.py        builds data/careers.csv from O*NET
  fairness_audit.py       the fairness check above
tests/                    23 pytest tests
.github/workflows/        rebuilds career data from O*NET automatically
```

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py
pytest                      # pip install -r requirements-dev.txt first
```

## Data sources
- **Colleges:** U.S. Department of Education [College Scorecard](https://collegescorecard.ed.gov/data/) (public domain), via the [collegeScorecard](https://github.com/cran/collegeScorecard) and [scorecard-db](https://github.com/gadenbuie/scorecard-db) mirrors. Net price, admissions, test scores, graduation rates, earnings, and majors.
- **Careers:** This app incorporates information from the [O*NET Database](https://www.onetcenter.org/database.html) by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA), used under the [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license. O*NET® is a trademark of USDOL/ETA.
- **Aid rules:** [FSA](https://fsapartners.ed.gov/), [HESC](https://hesc.ny.gov/), [SUNY EOP](https://www.suny.edu/attend/academics/eop/).

All aid figures are estimates for planning. Students get their real award from the FAFSA or the NYS Dream Act application.

## Background
I first built a college-matching tool during my 2026 Tech & Data internship at a New York education nonprofit. This is an independent rebuild from scratch: new code, public data only, with tests and a fairness audit added.

Built by **Doussouba Diakite**, Computer Engineering Technology, CUNY City Tech · [LinkedIn](https://www.linkedin.com/in/doussouba-diakite-a11087324)
