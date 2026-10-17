"""Turn what a student types ("nursing", "coding") into CIP families.

CIP = Classification of Instructional Programs, the federal code list for
majors. College Scorecard reports, for every school, the share of degrees
awarded in each 2-digit CIP family (PCIP11 = computer science, etc.).
"""
from __future__ import annotations

from difflib import get_close_matches

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
    # computing & engineering
    ("computer engineering", ["14", "11"]), ("electrical engineering", ["14"]), ("mechanical engineering", ["14"]),
    ("civil engineering", ["14"]), ("chemical engineering", ["14"]), ("biomedical engineering", ["14", "26"]),
    ("industrial engineering", ["14"]), ("aerospace", ["14"]), ("robotics", ["14", "15"]),
    ("engineering technology", ["15"]), ("electronics", ["15", "14"]), ("mechatronics", ["15"]),
    ("software", ["11"]), ("computer science", ["11"]), ("computer", ["11"]), ("coding", ["11"]),
    ("programming", ["11"]), ("web development", ["11"]), ("game design", ["11", "50"]), ("video game", ["11", "50"]),
    ("cybersecurity", ["11", "43"]), ("cyber", ["11", "43"]), ("data science", ["11", "27"]), ("data analytics", ["11", "27", "52"]),
    ("information technology", ["11"]), ("information systems", ["11", "52"]), ("artificial intelligence", ["11"]),
    ("machine learning", ["11", "27"]), ("networking", ["11"]), ("engineer", ["14"]),
    # health
    ("nursing", ["51"]), ("nurse", ["51"]), ("pre-med", ["26", "51"]), ("premed", ["26", "51"]), ("medicine", ["51", "26"]),
    ("doctor", ["51", "26"]), ("pharmacy", ["51"]), ("public health", ["51"]), ("dental", ["51"]), ("dentist", ["51"]),
    ("physical therapy", ["51"]), ("occupational therapy", ["51"]), ("radiology", ["51"]), ("sonography", ["51"]),
    ("nutrition", ["51", "19"]), ("dietetics", ["51", "19"]), ("kinesiology", ["31", "26"]), ("exercise science", ["31", "26"]),
    ("sports medicine", ["31", "51"]), ("physician assistant", ["51"]), ("paramedic", ["51"]), ("emt", ["51"]),
    ("health", ["51"]),
    # sciences & math
    ("biology", ["26"]), ("biochem", ["26", "40"]), ("neuroscience", ["26", "42"]), ("genetics", ["26"]),
    ("marine biology", ["26"]), ("zoology", ["26"]), ("ecology", ["26", "03"]), ("forensic", ["43", "40"]),
    ("chemistry", ["40"]), ("physics", ["40"]), ("astronomy", ["40"]), ("geology", ["40"]), ("earth science", ["40"]),
    ("meteorology", ["40"]), ("mathematics", ["27"]), ("math", ["27"]), ("statistics", ["27"]), ("actuarial", ["27", "52"]),
    ("environmental", ["03", "26"]), ("sustainability", ["03", "30"]), ("forestry", ["03"]), ("agriculture", ["01"]),
    ("veterinary", ["01", "51"]), ("animal science", ["01"]),
    # business
    ("accounting", ["52"]), ("finance", ["52"]), ("marketing", ["52"]), ("management", ["52"]),
    ("entrepreneurship", ["52"]), ("human resources", ["52"]), ("supply chain", ["52"]), ("real estate", ["52"]),
    ("hospitality", ["52"]), ("hotel", ["52"]), ("fashion merchandising", ["52", "50"]), ("business", ["52"]),
    # social sciences & humanities
    ("anthropology", ["45"]), ("archaeology", ["45"]), ("economics", ["45"]), ("political science", ["45"]),
    ("international relations", ["45"]), ("government", ["45"]), ("sociology", ["45"]), ("geography", ["45"]),
    ("urban studies", ["45", "04"]), ("social science", ["45"]), ("psychology", ["42"]), ("counseling", ["42", "51"]),
    ("social work", ["44"]), ("public policy", ["44"]), ("public administration", ["44"]), ("nonprofit", ["44", "52"]),
    ("criminal justice", ["43"]), ("criminology", ["43", "45"]), ("police", ["43"]), ("fire science", ["43"]),
    ("homeland security", ["43"]), ("pre-law", ["22", "45"]), ("paralegal", ["22"]), ("law", ["22"]),
    ("african american studies", ["05"]), ("africana", ["05"]), ("black studies", ["05"]), ("latino", ["05"]),
    ("latinx", ["05"]), ("ethnic studies", ["05"]), ("gender studies", ["05"]), ("women's studies", ["05"]),
    ("philosophy", ["38"]), ("religion", ["38"]), ("theology", ["38", "39"]), ("history", ["54"]),
    ("english", ["23"]), ("literature", ["23"]), ("creative writing", ["23"]), ("writing", ["23"]),
    ("linguistics", ["16"]), ("spanish", ["16"]), ("french", ["16"]), ("chinese", ["16"]), ("arabic", ["16"]),
    ("japanese", ["16"]), ("languages", ["16"]), ("translation", ["16"]), ("liberal arts", ["24"]),
    ("undecided", ["24"]), ("general studies", ["24"]),
    # education
    ("early childhood", ["13"]), ("special education", ["13"]), ("education", ["13"]), ("teaching", ["13"]),
    ("teacher", ["13"]),
    # media & arts
    ("journalism", ["09"]), ("communication", ["09"]), ("public relations", ["09"]), ("advertising", ["09", "52"]),
    ("media", ["09", "10"]), ("broadcasting", ["09", "10"]), ("film", ["50", "09"]), ("photography", ["50"]),
    ("animation", ["50", "10"]), ("graphic design", ["50"]), ("fashion design", ["50"]), ("fashion", ["50", "52"]),
    ("interior design", ["50", "04"]), ("theater", ["50"]), ("theatre", ["50"]), ("dance", ["50"]), ("acting", ["50"]),
    ("music", ["50"]), ("fine art", ["50"]), ("art history", ["50"]), ("art", ["50"]), ("design", ["50", "04"]),
    ("architecture", ["04"]),
    # trades & services
    ("culinary", ["12"]), ("cosmetology", ["12"]), ("chef", ["12"]), ("construction", ["46"]), ("electrician", ["46"]),
    ("plumbing", ["46"]), ("hvac", ["47"]), ("automotive", ["47"]), ("mechanic", ["47"]), ("welding", ["48"]),
    ("aviation", ["49"]), ("pilot", ["49"]), ("maritime", ["49"]),
]

PHRASES = [p for p, _ in KEYWORDS]
LOOKUP = dict(KEYWORDS)


def cip_families_for(text: str) -> list[str]:
    """Return 2-digit CIP families for a typed major. Empty list = no match.

    1. a known phrase inside what they typed ("BS in nursing" -> nursing)
    2. close spelling ("anthropolopy" -> anthropology), so typos still work
    3. an official family name ("social sciences")
    """
    t = (text or "").strip().lower()
    if not t:
        return []
    for phrase, fams in KEYWORDS:
        if phrase in t:
            return fams
    words = t.replace("-", " ").split()
    candidates = [t] + [" ".join(words[i:i + n]) for n in (3, 2, 1) for i in range(len(words) - n + 1)]
    for c in candidates:
        close = get_close_matches(c, PHRASES, n=1, cutoff=0.84)
        if close and len(c) >= 4:
            return LOOKUP[close[0]]
    for code, name in CIP_FAMILIES.items():  # fall back to official family names
        if t in name.lower() or name.lower() in t:
            return [code]
    return []


def suggest_spelling(text: str) -> str | None:
    """The known major a typo was matched to, to show the student ("Showing results for anthropology")."""
    t = (text or "").strip().lower()
    if not t or any(p in t for p in PHRASES):
        return None
    close = get_close_matches(t, PHRASES, n=1, cutoff=0.84)
    return close[0] if close else None


AI_TOOL = {"name": "pick_major_families",
           "description": "Pick the federal major families (CIP) that best fit the student's intended major.",
           "input_schema": {"type": "object", "properties": {
               "families": {"type": "array", "items": {"type": "string", "enum": list(CIP_FAMILIES)},
                            "minItems": 0, "maxItems": 2,
                            "description": "1-2 codes; empty if it isn't a field of study"}},
               "required": ["families"]}}


def ai_families(text: str, api_key: str | None = None, client=None) -> list[str]:
    """Last resort for majors the keyword list doesn't know ("basket weaving", "ethnomusicology").

    Claude can only answer with codes from the official CIP list (enforced by the tool's enum
    and checked again here), so it can't invent a category.
    """
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    from .advisor import MODEL
    menu = "\n".join(f"{c}: {n}" for c, n in CIP_FAMILIES.items())
    resp = client.messages.create(
        model=MODEL, max_tokens=200, tools=[AI_TOOL], tool_choice={"type": "tool", "name": "pick_major_families"},
        messages=[{"role": "user", "content": f"Intended major: {text[:100]!r}\n\nFamilies:\n{menu}"}])
    picked = next(b.input for b in resp.content if b.type == "tool_use").get("families", [])
    return [c for c in picked if c in CIP_FAMILIES][:2]


# Majors that line up with each interest type (Holland / RIASEC), for undecided students.
# Every entry is a phrase in KEYWORDS, so clicking one runs the normal major matching.
INTEREST_MAJORS = {
    "R": ["engineering technology", "mechanical engineering", "construction", "environmental", "automotive"],
    "I": ["biology", "computer science", "chemistry", "data science", "psychology"],
    "A": ["graphic design", "film", "music", "english", "architecture"],
    "S": ["nursing", "education", "social work", "psychology", "public health"],
    "E": ["business", "marketing", "political science", "pre-law", "entrepreneurship"],
    "C": ["accounting", "finance", "information systems", "data analytics", "paralegal"],
}


def majors_for_interests(top_letters: list[str], k: int = 6) -> list[str]:
    """Interleave suggestions from the student's top interest types, no repeats."""
    lists = [INTEREST_MAJORS[L] for L in top_letters if L in INTEREST_MAJORS]
    out = []
    for i in range(max((len(x) for x in lists), default=0)):
        for x in lists:
            if i < len(x) and x[i] not in out:
                out.append(x[i])
    return out[:k]
