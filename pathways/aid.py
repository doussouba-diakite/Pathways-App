"""Financial aid screening for New York students.

Rule-based on purpose: these are published eligibility rules, and a student
should be able to see exactly which rule applied. Amounts are ESTIMATES for
planning; the FAFSA, TAP, and Dream Act applications decide the real award.

Update these numbers every August. Checked October 2026:
  Pell       2026-27 max $7,395, min $740 (FSA Dear Colleague Letter GEN-26-01)
  NY TAP     up to $5,665, at least $1,000, income limit $125,000 NYS net taxable
             (hesc.ny.gov/find-aid/nys-grants-scholarships/tuition-assistance-program-tap)
  EOP        SUNY 2025-26 income guidelines (suny.edu/attend/academics/eop)
             HEOP and CUNY SEEK use similar state guidelines; confirm with each campus.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PELL_MAX = 7_395
PELL_MIN = 740
TAP_MAX = 5_665
TAP_MIN = 1_000
TAP_INCOME_LIMIT = 125_000

# Opportunity program income ceilings by household size (SUNY EOP, 2025-26).
# Households above 8: add $9,953 per person.
OPP_LIMITS = {1: 27_861, 2: 37_814, 3: 47_767, 4: 57_720, 5: 67_673, 6: 77_626, 7: 87_579, 8: 97_532}
OPP_EXTRA_PERSON = 9_953


@dataclass
class AidInput:
    income: float
    household: int = 4
    ny_resident: bool = True
    status: str = "Citizen or permanent resident"  # | DACA | Undocumented | Other
    first_gen: bool = False


@dataclass
class AidResult:
    pell: int = 0
    tap: int = 0
    dream_act: bool = False
    opportunity_programs: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.pell + self.tap


def estimate_pell(income: float, household: int) -> int:
    """Simplified sliding scale. Real Pell uses the Student Aid Index from the FAFSA."""
    adj = income - max(0, household - 4) * 6_000  # bigger families stretch the same income
    if adj <= 30_000:
        return PELL_MAX
    if adj >= 75_000:
        return 0
    share = 1 - (adj - 30_000) / 45_000
    return max(PELL_MIN, int(round(PELL_MAX * share / 100) * 100))


def estimate_tap(income: float) -> int:
    if income > TAP_INCOME_LIMIT:
        return 0
    if income <= 10_000:
        return TAP_MAX
    share = max(0.0, 1 - (income - 10_000) / (TAP_INCOME_LIMIT - 10_000))
    return max(TAP_MIN, int(round(TAP_MAX * share / 100) * 100))


def opportunity_limit(household: int) -> int:
    if household <= 8:
        return OPP_LIMITS[max(1, household)]
    return OPP_LIMITS[8] + (household - 8) * OPP_EXTRA_PERSON


def screen(a: AidInput) -> AidResult:
    r = AidResult()
    federal_ok = a.status in ("Citizen or permanent resident",)
    if federal_ok:
        r.pell = estimate_pell(a.income, a.household)
        r.notes.append("Federal Pell Grant: file the FAFSA to get your real amount.")
    else:
        r.notes.append("Federal aid like Pell requires citizenship or eligible noncitizen status.")

    if a.ny_resident:
        if federal_ok:
            r.tap = estimate_tap(a.income)
            if r.tap:
                r.notes.append("NY TAP: apply through HESC after the FAFSA.")
        if a.status in ("DACA", "Undocumented"):
            r.dream_act = True
            r.tap = estimate_tap(a.income)
            r.notes.append("NYS Dream Act: you can receive TAP and other state aid. "
                           "Apply on the Dream Act application, not the FAFSA.")
        if a.income <= opportunity_limit(a.household):
            r.opportunity_programs = True
            r.notes.append("You may qualify for HEOP (private), EOP (SUNY), or SEEK / College Discovery "
                           "(CUNY): extra money, tutoring, and counseling. Check the box on your application.")
    if a.first_gen:
        r.notes.append("First-generation students: ask each school about first-gen scholarships and mentoring.")
    return r
