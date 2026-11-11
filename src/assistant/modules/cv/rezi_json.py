"""Rezi's resume JSON as plain sections (`CvContent.from_rezi`, for `cv.compare`), and back.

**Rezi's real format** (seen live 2026-11-07; `get_resume_format` lists the fields): `read_resume`
answers `{id, name, hiddenSections, ..., data}`; `data` has `contact` (fields, `city`/`state`/
`country` maybe `{label, value}`), `summary: {summary}`, and list sections as `{<uuid>: {fields...,
index, hide?}}`. `write_resume` takes the same object (`{name, jobTitle, jobCompany, jobDescription,
data}`). `read_real` reads it into the CV's lines the way the `.odt` writes them (`Role, Company |
Duration`, `• ` bullets; education `Degree, Date GPA : x` then `School, Place`), and `write_rezi`
writes a CV's sections into it, so a CV goes to Rezi and back unchanged.

**Anything else** is read tolerantly: sections by name (`ALIASES`) at the top, under `sections`, or
in a list of `{type|name|title, items}` blocks; ISO dates (`2020-01`) become `Jan 2020`. Keys it
can't place come back as `skipped`, so nothing is lost silently.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from assistant.modules.cv.content import CvContent

ALIASES: dict[str, tuple[str, ...]] = {
    "contact": ("contact", "contacts", "contactinfo", "contactinformation", "personal", "personalinfo",
                "personaldetails", "personalinformation", "basics", "header"),
    "summary": ("summary", "profile", "about", "objective", "introduction", "professionalsummary"),
    "skills": ("skills", "skill", "technicalskills", "competencies", "coreskills", "keyskills"),
    "experience": ("experience", "experiences", "work", "workexperience", "employment", "professionalexperience",
                   "jobs", "additionalexperience"),
    "projects": ("projects", "project"),
    "education": ("education", "studies", "degrees"),
    "awards": ("awards", "award", "honors", "honours", "accomplishments", "achievements", "certifications",
               "certificates"),
    "publications": ("publications", "publication", "papers"),
}  # fmt: skip
_SECTION_OF = {alias: name for name, aliases in ALIASES.items() for alias in aliases}

_WRAPPERS = ("resume", "content", "data")
_META = {"id", "resumeid", "_id", "name", "title", "resumename", "createdat", "updatedat", "template",
         "language", "locale", "metadata", "meta", "settings", "score", "userid", "ownerid", "version"}  # fmt: skip
_TITLE = ("title", "position", "role", "jobtitle", "degree", "studytype", "name", "label", "award")
_ORG = ("company", "employer", "organization", "organisation", "institution", "school", "university",
        "issuer", "publisher", "awarder")  # fmt: skip
_PLACE = ("location", "city", "place")
_START = ("start", "startdate", "from", "begin")
_END = ("end", "enddate", "to", "until")
_DATE = ("date", "dates", "period", "year", "graduationdate", "releasedate")
_BULLETS = ("highlights", "bullets", "achievements", "responsibilities", "details", "points", "items", "keywords",
            "courses", "description", "summary")  # fmt: skip
_BLOCK_NAME = ("type", "key", "section", "name", "title", "heading")
_BLOCK_ITEMS = ("items", "entries", "content", "values", "lines", "data")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _key(key: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(key).lower()).replace("_", "")


def read_rezi(data: Any) -> tuple[CvContent, list[str]]:
    """The sections found in Rezi's resume JSON, and the keys it couldn't place (`skipped`).
    Rezi's real format (`read_resume`'s answer, or its `data`) is read exactly (`read_real`);
    anything else tolerantly. ValueError when nothing in it looks like a resume section."""
    if (real := rezi_data(data)) is not None:
        return read_real(real, data.get("hiddenSections", ()) if isinstance(data, dict) else ())
    found: dict[str, list[str]] = {}
    skipped: list[str] = []
    for name, value in _sections(_unwrap(data), skipped):
        found.setdefault(name, []).extend(_lines(value, name))
    if not found:
        raise ValueError(f"no resume sections found in Rezi's data (keys: {_keys(data)}); known: {list(ALIASES)}")
    return CvContent(sections={n: tuple(lines) for n, lines in found.items()}), skipped


def _keys(data: Any) -> list[str]:
    return list(data)[:20] if isinstance(data, dict) else [type(data).__name__]


def _unwrap(data: Any) -> Any:
    for _ in range(3):
        if isinstance(data, dict) and not any(_key(k) in _SECTION_OF or _key(k) == "sections" for k in data):
            inner = next((data[k] for k in data if _key(k) in _WRAPPERS and isinstance(data[k], (dict, list))), None)
            if inner is None:
                break
            data = inner
    return data


def _sections(data: Any, skipped: list[str]):
    """(section, value) for each section found; keys it can't place go to `skipped`."""
    if isinstance(data, dict):
        for key, value in data.items():
            k = _key(key)
            if k == "sections":
                yield from _sections(value, skipped)
            elif k in _SECTION_OF:
                yield _SECTION_OF[k], value
            elif k not in _META and value not in (None, "", [], {}):
                skipped.append(str(key))
    elif isinstance(data, list):
        for i, block in enumerate(data):
            name = _block_section(block)
            if name is None:
                skipped.append(f"[{i}]")
                continue
            items = next((block[k] for k in block if _key(k) in _BLOCK_ITEMS), None)
            if items is None:
                items = {k: v for k, v in block.items() if _key(k) not in _BLOCK_NAME}
            yield name, items


def _block_section(block: Any) -> str | None:
    if not isinstance(block, dict):
        return None
    for k in block:
        if _key(k) in _BLOCK_NAME and _key(block[k]) in _SECTION_OF:
            return _SECTION_OF[_key(block[k])]
    return None


def _date(value: Any) -> str:
    text = str(value).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?(?:T.*)?", text)
    if m and 1 <= int(m[2]) <= 12:
        return f"{_MONTHS[int(m[2]) - 1]} {m[1]}"
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", text)
    if m and 1 <= int(m[1]) <= 12:
        return f"{_MONTHS[int(m[1]) - 1]} {m[2]}"
    return text


def _text_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text).splitlines() if line.strip()]


def _lines(value: Any, section: str) -> list[str]:
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, (str, int, float)):
        return _text_lines(str(value))
    if isinstance(value, list):
        return [line for item in value for line in _lines(item, section)]
    if isinstance(value, dict):
        return _contact(value) if section == "contact" else _entry(value, section)
    return []


def _pick(entry: dict[str, Any], names: tuple[str, ...], used: set[str]) -> str:
    for key, value in entry.items():
        if _key(key) in names and key not in used and isinstance(value, (str, int, float)) and str(value).strip():
            used.add(key)
            return str(value).strip()
    return ""


def _entry(entry: dict[str, Any], section: str) -> list[str]:
    used: set[str] = set()
    head = [p for p in (_pick(entry, _TITLE, used), _pick(entry, _ORG, used), _pick(entry, _PLACE, used)) if p]
    start, end = _pick(entry, _START, used), _pick(entry, _END, used)
    current = next((k for k in entry if _key(k) in ("current", "iscurrent", "present") and entry[k] is True), None)
    if current:
        used.add(current)
        end = end or "Present"
    dates = " – ".join(_date(d) for d in (start, end) if d) or _date(_pick(entry, _DATE, used))
    lines = [", ".join(head) + (f" | {dates}" if dates else "")] if head or dates else []
    for key, value in entry.items():
        if key in used or _key(key) in ("id", "_id", "order", "position_index", "visible", "hidden"):
            continue
        if _key(key) in _BULLETS and isinstance(value, list):
            lines += [f"• {line}" for item in value for line in _lines(item, section)]
        else:
            lines += _lines(value, section)
    return lines


def _contact(contact: dict[str, Any]) -> list[str]:
    used: set[str] = set()
    name = _pick(contact, ("name", "fullname"), used)
    first, last = _pick(contact, ("firstname",), used), _pick(contact, ("lastname",), used)
    lines = [name or " ".join(p for p in (first, last) if p)]
    for key, value in contact.items():
        if key not in used:
            lines += _lines(value, "experience") if isinstance(value, dict) else _lines(value, "contact")
    return [line for line in lines if line]


# --- Rezi's real format ------------------------------------------------------------------------------------

# Rezi's section -> the CV's section. Rezi splits out military/research/teaching/involvement; the CVs keep
# them under experience. References aren't on the one page.
REZI_SECTIONS: dict[str, str] = {
    "contact": "contact", "summary": "summary", "skills": "skills", "experience": "experience",
    "military": "experience", "research": "experience", "involvement": "experience", "teaching": "experience",
    "projects": "projects", "education": "education", "coursework": "education", "awards": "awards",
    "certification": "awards", "publication": "publications",
}  # fmt: skip
# Per Rezi section: the fields of an entry's first line, then its date fields.
_HEAD: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "experience": (("role", "company", "location"), ("duration",)),
    "military": (("title", "branch", "location"), ("duration",)),
    "research": (("position", "project"), ("duration",)),
    "involvement": (("role", "organization", "location"), ("duration",)),
    "teaching": (("position", "course", "institution"), ("duration",)),
    "projects": (("title", "organization"), ("duration", "date")),
    "coursework": (("name", "department"), ("date",)),
    "awards": (("name", "institution"), ("date",)),
    "certification": (("name", "department"), ("date",)),
    "publication": (("title", "conference"), ("date",)),
}  # fmt: skip
_BULLETED = ("awards", "certification", "publication")  # one "• " line per entry, as on the CVs
_DEGREE = re.compile(r"(?P<q>.+?),\s*(?P<d>(?:Expected\s+)?(?:[A-Z][a-z]+\.?\s+)?\d{4})(?:\s+GPA\s*:?\s*(?P<g>.+))?")
_BULLET = re.compile(r"^\s*[•·\-*]\s*")


def rezi_data(data: Any) -> dict[str, Any] | None:
    """The `data` of a resume in Rezi's real format (the whole answer or its `data`), else None."""
    inner = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
    if not isinstance(inner, dict):
        return None
    for key, value in inner.items():
        if key == "summary" and isinstance(value, dict) and "summary" in value:
            return inner
        if key in REZI_SECTIONS and isinstance(value, dict) and value and all(
                isinstance(e, dict) and "index" in e for e in value.values()):  # fmt: skip
            return inner
    return None


def _value(value: Any) -> str:
    """A field as text: `{label, value}` gives its value."""
    if isinstance(value, dict):
        value = value.get("value") or value.get("label") or ""
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def entries(section: Any) -> list[tuple[str, dict[str, Any]]]:
    """A list section's (uuid, entry) in Rezi's order (`index`), hidden ones left out."""
    if not isinstance(section, dict):
        return []
    found = [(k, e) for k, e in section.items() if isinstance(e, dict) and not e.get("hide")]
    return sorted(found, key=lambda kv: kv[1].get("index", 0) if isinstance(kv[1].get("index"), int) else 0)


def _bullets(text: str) -> list[str]:
    return [f"• {_BULLET.sub('', line)}" for line in _text_lines(text) if _BULLET.sub("", line)]


def _real_entry(kind: str, entry: dict[str, Any]) -> list[str]:
    if kind == "skills":
        return _text_lines(_value(entry.get("skill")))
    if kind == "education":
        q, d, g = (_value(entry.get(k)) for k in ("qualification", "date", "gpa"))
        first = ", ".join(p for p in (q, d) if p) + (f" GPA : {g}" if g else "")
        place = ", ".join(p for p in (_value(entry.get("institution")), _value(entry.get("location"))) if p)
        minor = _value(entry.get("minor"))
        return [line for line in (first, place, f"Minor: {minor}" if minor else "") if line] + _bullets(
            _value(entry.get("description")))  # fmt: skip
    heads, dates = _HEAD.get(kind, ((), ()))
    head: list[str] = []
    for field in heads:
        text = _value(entry.get(field))
        if text and text not in head:  # Rezi often repeats the company as the location
            head.append(text)
    when = next((t for t in (_value(entry.get(f)) for f in dates) if t), "")
    line = ", ".join(head) + (f" | {when}" if when else "")
    if kind in _BULLETED:
        return ([f"• {line}"] if line else []) + _bullets(_value(entry.get("description")))
    lines = [line] if line else []
    if url := _value(entry.get("url")):
        lines.append(url)
    return lines + _bullets(_value(entry.get("description")))


def _real_contact(contact: dict[str, Any]) -> list[str]:
    place = ", ".join(p for p in (_value(contact.get("city")), _value(contact.get("state"))) if p) or _value(
        contact.get("country"))  # fmt: skip
    parts = [_value(contact.get(k)) for k in ("phone", "email", "linkedin", "website")] + [place]
    return [line for line in (_value(contact.get("name")), " | ".join(p for p in parts if p)) if line]


def read_real(data: dict[str, Any], hidden: Any = ()) -> tuple[CvContent, list[str]]:
    """A resume's `data` in Rezi's real format as the CV's sections; sections it doesn't map and
    sections Rezi hides (`hiddenSections`) come back as `skipped`."""
    hidden = {str(h) for h in hidden} if isinstance(hidden, (list, tuple, set)) else set()
    found: dict[str, list[str]] = {}
    skipped: list[str] = []
    for key, value in data.items():
        if value in (None, "", {}, []):
            continue
        name = REZI_SECTIONS.get(key)
        if name is None or key in hidden:
            skipped.append(key)
        elif key == "contact":
            found.setdefault(name, []).extend(_real_contact(value) if isinstance(value, dict) else [])
        elif key == "summary":
            found.setdefault(name, []).extend(_text_lines(_value(value.get("summary") if isinstance(value, dict)
                                                                 else value)))  # fmt: skip
        else:
            found.setdefault(name, []).extend(line for _, e in entries(value) for line in _real_entry(key, e))
    found = {n: lines for n, lines in found.items() if lines}
    if not found:
        raise ValueError(f"no resume sections found in Rezi's data (keys: {_keys(data)})")
    return CvContent(sections={n: tuple(lines) for n, lines in found.items()}), skipped


def split_head(line: str) -> tuple[str, str, str]:
    """`Role, Company | Dates` -> (role, company, dates); the role ends at the first comma."""
    head, _, when = line.rpartition(" | ") if " | " in line else (line, "", "")
    first, _, rest = head.partition(", ")
    return first.strip(), rest.strip(), when.strip()


def _contact_fields(lines: tuple[str, ...], left_out: list[str]) -> dict[str, Any]:
    fields: dict[str, Any] = {"name": lines[0].strip()} if lines else {}
    for line in lines[1:]:
        for part in (p.strip() for p in line.split("|")):
            if not part:
                continue
            if "@" in part and " " not in part:
                fields.setdefault("email", part)
            elif "linkedin" in part.lower():
                fields.setdefault("linkedin", part)
            elif re.fullmatch(r"[\d\s()+.\-]{7,}", part):
                fields.setdefault("phone", part)
            elif re.fullmatch(r"(https?://)?[\w.-]+\.[a-z]{2,}(/\S*)?", part, re.I):
                fields.setdefault("website", part)
            elif m := re.fullmatch(r"([^,]+),\s*([^,]+)", part):
                fields.setdefault("city", m[1].strip())
                fields.setdefault("state", m[2].strip())
            else:
                left_out.append(part)  # a headline like "XR Software Engineer": Rezi's contact has no field for it
    return fields


def _keyed(kind: str, items: list[dict[str, Any]], keys: list[str]) -> dict[str, Any]:
    """Entries keyed like Rezi's: the resume's own uuids first (`keys`, an update), then new ones;
    its entries beyond the new ones are hidden, so an update never leaves an old line showing."""
    out: dict[str, Any] = {}
    for i, item in enumerate(items):
        out[keys[i] if i < len(keys) else str(uuid.uuid4())] = item | {"index": i}
    for i, key in enumerate(keys[len(items):], start=len(items)):
        out[key] = {"index": i, "hide": True}
    return out


def _section_items(name: str, lines: tuple[str, ...]) -> tuple[str, list[dict[str, Any]]]:
    """One CV section as (Rezi section, its entries)."""
    plain = [line.strip() for line in lines if line.strip()]
    if name == "skills":
        return "skills", [{"skill": line} for line in plain]
    if name in ("awards", "publications"):
        field = "name" if name == "awards" else "title"
        return ("awards" if name == "awards" else "publication"), [{field: _BULLET.sub("", line)} for line in plain]
    items: list[dict[str, Any]] = []
    for line in plain:
        if _BULLET.match(line):
            if not items:
                items.append({})
            items[-1].setdefault("_bullets", []).append(_BULLET.sub("", line))
        elif name == "education":
            if items and "institution" not in items[-1] and "_bullets" not in items[-1]:
                school, _, place = line.partition(", ")
                items[-1] |= {"institution": school.strip()} | ({"location": place.strip()} if place.strip() else {})
            elif m := _DEGREE.fullmatch(line):
                items.append({"qualification": m["q"].strip(), "date": m["d"].strip()}
                             | ({"gpa": m["g"].strip()} if m["g"] else {}))  # fmt: skip
            else:
                items.append({"qualification": line})
        else:
            first, rest, when = split_head(line)
            title, org = ("role", "company") if name == "experience" else ("title", "organization")
            items.append({title: first} | ({org: rest} if rest else {}) | ({"duration": when} if when else {}))
    for item in items:
        if bullets := item.pop("_bullets", None):
            item["description"] = "\n".join(bullets)
    return name, items


def write_rezi(content: CvContent, name: str, job_title: str = "", job_company: str = "", job_description: str = "",
               existing: Any = None) -> tuple[dict[str, Any], list[str]]:  # fmt: skip
    """The CV's sections as Rezi's resume object for `write_resume`, and the lines Rezi has no field
    for (`left_out`). `existing`: the resume being updated (`read_resume`'s answer), whose entry
    uuids are reused so the update replaces its entries instead of adding to them."""
    old = rezi_data(existing) or {}
    left_out: list[str] = []
    data: dict[str, Any] = {}
    for section, lines in content.sections.items():
        if not any(line.strip() for line in lines):
            continue
        if section == "contact":
            data["contact"] = _contact_fields(tuple(line for line in lines if line.strip()), left_out)
        elif section == "summary":
            data["summary"] = {"summary": "\n".join(line.strip() for line in lines if line.strip())}
        else:
            kind, items = _section_items(section, lines)
            keys = [k for k, _ in entries(old.get(kind))]
            data[kind] = _keyed(kind, items, keys)
    resume: dict[str, Any] = {"name": name, "data": data}
    for key, value in (("jobTitle", job_title), ("jobCompany", job_company), ("jobDescription", job_description)):
        if value:
            resume[key] = value
    return resume, left_out
