import re
from typing import Dict, List

# Minimal skill list (we will expand later)
DEFAULT_SKILLS = [
    "python", "sql", "tensorflow", "pytorch", "keras", "fastapi", "docker",
    "postgresql", "redis", "mlflow", "nlp", "spacy", "aws", "azure", "git"
]

SECTION_HEADERS = {
    "skills": ["skills", "technical skills"],
    "education": ["education", "academic background"],
    "experience": ["experience", "work experience", "professional experience"],
}

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def extract_section(text: str, header_variants: List[str]) -> str:
    """
    Very simple section splitter:
    finds a header and takes text until the next all-caps-like header.
    """
    t = text
    lower = t.lower()

    start = -1
    for h in header_variants:
        idx = lower.find(h.lower())
        if idx != -1:
            start = idx
            break
    if start == -1:
        return ""

    # take a window after header
    chunk = t[start:start + 2500]

    # stop at another common header keyword if present
    stop_keywords = ["education", "experience", "projects", "skills", "certifications", "summary"]
    chunk_lower = chunk.lower()
    stops = [chunk_lower.find(k) for k in stop_keywords if chunk_lower.find(k) != -1]
    # ignore first occurrence (it's the header we matched), so pick second smallest > 0
    stops = sorted([s for s in stops if s > 0])
    if len(stops) >= 2:
        chunk = chunk[:stops[1]]

    return normalize(chunk)

def extract_skills(text: str, skill_list: List[str] = DEFAULT_SKILLS) -> List[str]:
    t = text.lower()
    found = []
    for s in skill_list:
        if re.search(rf"\b{re.escape(s.lower())}\b", t):
            found.append(s)
    return sorted(set(found))

def extract_bullets(section_text: str) -> List[str]:
    if not section_text:
        return []
    # split on common bullet patterns
    parts = re.split(r"(?:\n|•|-|\u2022)+", section_text)
    bullets = [normalize(p) for p in parts if normalize(p) and len(normalize(p)) > 5]
    return bullets[:12]

def parse_resume(raw_text: str) -> Dict:
    skills_section = extract_section(raw_text, SECTION_HEADERS["skills"])
    edu_section = extract_section(raw_text, SECTION_HEADERS["education"])
    exp_section = extract_section(raw_text, SECTION_HEADERS["experience"])

    skills = extract_skills(skills_section if skills_section else raw_text)

    return {
        "skills": skills,
        "education": extract_bullets(edu_section),
        "experience": extract_bullets(exp_section),
        "sections_found": {
            "skills": bool(skills_section),
            "education": bool(edu_section),
            "experience": bool(exp_section),
        },
    }
