"""Turn what a student types ("nursing", "coding") into CIP families.

CIP = Classification of Instructional Programs, the federal code list for
majors. College Scorecard reports, for every school, the share of degrees
awarded in each 2-digit CIP family (PCIP11 = computer science, etc.).
"""
from __future__ import annotations

CIP_FAMILIES = {
    "01": "Agriculture", "03": "Natural Resources", "04": "Architecture",
    "05": "Ethnic & Gender Studies", "09": "Communication & Journalism",
    "10": "Communications Technology", "11": "Computer Science", "12": "Culinary & Personal Services",
    "13": "Education", "14": "Engineering", "15": "Engineering Technology", "16": "Languages",
    "19": "Family & Consumer Science", "22": "Law", "23": "English", "24": "Liberal Arts",
    "26": "Biology", "27": "Math & Statistics", "30": "Interdisciplinary", "31": "Parks & Recreation",
    "38": "Philosophy & Religion", "40": "Physical Sciences", "42": "Psychology",
    "43": "Criminal Justice & Protective Services", "44": "Public Administration & Social Work",
    "45": "Social Sciences", "46": "Construction Trades", "47": "Mechanic & Repair",
    "48": "Precision Production", "49": "Transportation", "50": "Visual & Performing Arts",
    "51": "Health Professions", "52": "Business", "54": "History",
}

# Most specific phrases first; checked as substrings of what the student typed.
KEYWORDS = [
    ("computer engineering", ["14", "11"]), ("software", ["11"]), ("computer", ["11"]),
    ("coding", ["11"]), ("programming", ["11"]), ("cyber", ["11", "43"]), ("data science", ["11", "27"]),
    ("information technology", ["11"]), ("artificial intelligence", ["11"]),
    ("engineering technology", ["15"]), ("engineer", ["14"]),
    ("nursing", ["51"]), ("nurse", ["51"]), ("pre-med", ["26", "51"]), ("medicine", ["51", "26"]),
    ("pharmacy", ["51"]), ("public health", ["51"]), ("health", ["51"]),
    ("biology", ["26"]), ("biochem", ["26", "40"]), ("neuroscience", ["26", "42"]),
    ("chemistry", ["40"]), ("physics", ["40"]), ("math", ["27"]), ("statistics", ["27"]),
    ("accounting", ["52"]), ("finance", ["52"]), ("marketing", ["52"]), ("business", ["52"]),
    ("economics", ["45"]), ("political science", ["45"]), ("sociology", ["45"]),
    ("psychology", ["42"]), ("social work", ["44"]), ("criminal justice", ["43"]),
    ("pre-law", ["22", "45"]), ("law", ["22"]),
    ("education", ["13"]), ("teaching", ["13"]), ("teacher", ["13"]),
    ("journalism", ["09"]), ("communication", ["09"]), ("film", ["50", "09"]),
    ("music", ["50"]), ("art", ["50"]), ("design", ["50", "04"]), ("architecture", ["04"]),
    ("english", ["23"]), ("writing", ["23"]), ("history", ["54"]), ("languages", ["16"]),
    ("culinary", ["12"]), ("construction", ["46"]), ("aviation", ["49"]), ("agriculture", ["01"]),
    ("environmental", ["03", "26"]),
]


def cip_families_for(text: str) -> list[str]:
    """Return 2-digit CIP families for a typed major. Empty list = no match."""
    t = (text or "").strip().lower()
    if not t:
        return []
    for phrase, fams in KEYWORDS:
        if phrase in t:
            return fams
    for code, name in CIP_FAMILIES.items():  # fall back to official family names
        if t in name.lower():
            return [code]
    return []
