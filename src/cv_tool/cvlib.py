"""CV Tool core: read base CVs, parse them, render the page, check it, export the PDF, read Rezi text.

The code lives in the repo (`src/cv_tool`); the data (jobs, inbox, outbox, rezi_requests, data\\confirmed_facts.json)
stays in `data_dir`, set by `configure()` from the app's config. The rules are the cv module's (`rules_dir`): the app
reads them, it keeps no copy.
"""
import base64
import datetime
import html
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import pymupdf

APP = os.path.dirname(os.path.abspath(__file__))  # code, static\ and assets\
FONT = os.path.join(APP, "assets", "SourceSans3-VF.ttf")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
DEFAULT_DATA = r"C:\Chang\Jobs\CV_Module\cv_tool"
DEFAULT_RULES = r"C:\Chang\Jobs\CV_Module\.claude\skills\cv-writing"


CV_PREFIX = "CV_Test_"  # the start of the user's CV file names (`cv_prefix`; the real one in the local config)


def configure(data_dir=DEFAULT_DATA, cv_dir=r"C:\Chang\Jobs\CV", rules_dir=DEFAULT_RULES, agent_work="", facts="",
              cv_prefix="CV_Test_"):  # fmt: skip
    """Point the app at its data folder, the base CVs (named `<cv_prefix>*`), the cv module's rules and
    the confirmed facts. Called at start. `facts` defaults to <data_dir>\\..\\data\\confirmed_facts.json
    when that exists (the cv module's workspace), else <data_dir>\\data\\confirmed_facts.json."""
    global ROOT, CV_DIR, JOBS, DATA, FACTS, INBOX, REZI_REQ, REZI_RES, OUTBOX, AGENT_WORK, RULES_DIR, CV_PREFIX, _corpus
    _corpus = None  # the CV folder may have changed: read it again
    CV_PREFIX = cv_prefix
    ROOT = os.path.abspath(data_dir)
    CV_DIR = os.path.abspath(cv_dir)
    RULES_DIR = os.path.abspath(rules_dir)
    JOBS = os.path.join(ROOT, "jobs")
    DATA = os.path.join(ROOT, "data")
    beside = os.path.join(os.path.dirname(ROOT), "data", "confirmed_facts.json")
    FACTS = os.path.abspath(facts) if facts else beside if os.path.isfile(beside) else os.path.join(DATA, "confirmed_facts.json")
    INBOX = os.path.join(ROOT, "inbox")
    REZI_REQ = os.path.join(ROOT, "rezi_requests")
    REZI_RES = os.path.join(REZI_REQ, "results")
    OUTBOX = os.path.join(ROOT, "outbox")
    AGENT_WORK = os.path.abspath(agent_work) if agent_work else os.path.join(os.path.dirname(ROOT), "work")
    os.makedirs(JOBS, exist_ok=True)


def rule_files():
    """The cv module's rule files: the skill's SKILL.md, then every .md in its rules\\ folder."""
    out = []
    skill = os.path.join(RULES_DIR, "SKILL.md")
    if os.path.isfile(skill):
        out.append(skill)
    sub = os.path.join(RULES_DIR, "rules")
    for d in (sub, RULES_DIR):
        if os.path.isdir(d):
            out += [os.path.join(d, n) for n in sorted(os.listdir(d))
                    if n.lower().endswith(".md") and n != "SKILL.md" and os.path.isfile(os.path.join(d, n))]
    return out


def rules():
    """The cv module's rules (read from the module's rules folder, no copy kept): file and first rule line."""
    out = []
    for p in rule_files():
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.read().split("\n")]
        meta = ("#", "---", "name:", "description:", "metadata:", "type:", "node_type:", "originSessionId:", "modified:")
        body = [l for l in lines if l and not l.startswith(meta)]
        out.append({"file": os.path.basename(p), "rule": body[0][:200] if body else ""})
    return {"dir": RULES_DIR, "rules": out}


# Page layout: settings in <data_dir>\page_settings.json, read at every render, line-fit measure and font
# check, so a change applies to the next print with no restart (user, 2026-11-10). A missing file or key,
# an unreadable file, or a value outside its range gives the default below. min_pt is the user's floor:
# text printed under it is a warning only, never a refusal (shorten or ask, never shrink).
PAGE_SETTINGS = "page_settings.json"
PAPERS = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}  # page width, height in pt
LAYOUT_DEFAULTS = {
    "paper": "letter",       # "letter" or "a4"
    "line_height": 1.15,     # line spacing (user, 2026-11-10, raised from 1.1)
    "body_pt": 10.0,         # body text: Summary, Skills, bullets, contact, titles, degrees, awards
    "name_pt": 15.0,         # the name at the top
    "heading_pt": 10.8,      # section headings
    "min_pt": 10.0,          # text printed under it is a warning (user, 2026-11-10, raised from 9)
    "bold_weight": 600,      # the name, headings, job titles, dates rows, degrees, awards
    "margin_top_pt": 36.0,   # top and bottom margin (0.5 in)
    "margin_side_pt": 36.0,  # left and right margin (0.5 in)
    "header_gap_pt": 4.0,    # space under the contact line
    "section_before_pt": 5.0,  # space above each section heading
    "section_after_pt": 2.5,   # space under each section heading
    "entry_gap_pt": 4.0,     # space after each job (a job followed by a tight one: 0.55 of it)
    "skill_gap_pt": 1.0,     # space after each Skills line
    "degree_gap_pt": 3.0,    # space after each degree
    "award_gap_pt": 1.5,     # space after each award
    "text_color": "#2e3a4b",  # body text and the heading rule
    "heading_rule_pt": 0.9,  # the line under each section heading
    "link_color": "#1F4E79",  # visible links
}
LAYOUT_RANGES = {"line_height": (1.0, 1.5), "body_pt": (8.0, 14.0), "name_pt": (10.0, 30.0),
                 "heading_pt": (8.0, 18.0), "min_pt": (6.0, 14.0), "bold_weight": (400, 900),
                 "margin_top_pt": (18.0, 72.0), "margin_side_pt": (18.0, 72.0),
                 "header_gap_pt": (0.0, 12.0), "section_before_pt": (0.0, 12.0), "section_after_pt": (0.0, 12.0),
                 "entry_gap_pt": (0.0, 12.0), "skill_gap_pt": (0.0, 6.0), "degree_gap_pt": (0.0, 8.0),
                 "award_gap_pt": (0.0, 6.0), "heading_rule_pt": (0.0, 3.0)}
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
LAYOUT_COLORS = ("text_color", "link_color")
FILL_TARGET = 0.92
E = html.escape
_font = None


def layout():
    """The page's layout settings, read from <data_dir>\\page_settings.json on every call (no cache), so a
    change applies to the next print with no restart. Each key falls back to LAYOUT_DEFAULTS on its own:
    missing, not a number, or outside LAYOUT_RANGES. An unreadable file gives all the defaults."""
    out = dict(LAYOUT_DEFAULTS)
    try:
        with open(os.path.join(ROOT, PAGE_SETTINGS), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return out
    if not isinstance(raw, dict):
        return out
    for k, (lo, hi) in LAYOUT_RANGES.items():
        v = raw.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi:
            out[k] = int(v) if k == "bold_weight" else float(v)
    for k in LAYOUT_COLORS:
        v = raw.get(k)
        if isinstance(v, str) and _COLOR.match(v):
            out[k] = v
    v = raw.get("paper")
    if isinstance(v, str) and v.strip().lower() in PAPERS:
        out["paper"] = v.strip().lower()
    return out


def page_size(lay=None):
    """The page's (width, height) in pt, from the paper setting."""
    lay = lay or layout()
    return PAPERS[lay["paper"]]


def text_width(lay=None):
    """The text column's width in pt: the page minus both side margins."""
    lay = lay or layout()
    return page_size(lay)[0] - 2 * lay["margin_side_pt"]


def text_height(lay=None):
    """The text column's height in pt: the page minus top and bottom margins."""
    lay = lay or layout()
    return page_size(lay)[1] - 2 * lay["margin_top_pt"]


def font():
    global _font
    if _font is None:
        _font = pymupdf.Font(fontfile=FONT)
    return _font


# ---------- base CVs

def list_cvs():
    return sorted(f for f in os.listdir(CV_DIR) if f.startswith(CV_PREFIX) and f.endswith(CV_TYPES))


CV_TYPES = (".pdf", ".odt", ".docx")  # the cv module sends PDFs; .odt and .docx still open by hand
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _inside(path, folder):
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(folder)]) == os.path.abspath(folder)
    except ValueError:
        return False


def odt_paras(name):
    """Paragraphs of a base CV (.pdf, .odt or .docx), from the CV folder or a job folder (uploaded copies)."""
    path = name if os.path.dirname(name) else os.path.join(CV_DIR, name)
    if not (_inside(path, CV_DIR) or _inside(path, JOBS)):
        raise PermissionError("only CVs in " + CV_DIR + " or a job folder")
    if path.lower().endswith(".pdf"):
        return pdf_paras(path)
    with zipfile.ZipFile(path) as z:
        if path.lower().endswith(".docx"):
            root, tags = ET.fromstring(z.read("word/document.xml")), (f"{{{W_NS}}}p",)
        else:
            root, tags = ET.fromstring(z.read("content.xml")), (f"{{{TEXT_NS}}}p", f"{{{TEXT_NS}}}h")
    out = []
    for el in root.iter():
        if el.tag in tags:
            t = "".join(el.itertext()).strip()
            if t:
                out.append(t)
    return out


def pdf_paras(path):
    """Lines of a text PDF as paragraphs, best effort (a job from the cv module brings its content, read
    with the module's own PDF reader, so this is only for a CV dropped in by hand). Bullets start a
    paragraph; a line that doesn't start one and follows a bullet joins it."""
    doc = pymupdf.open(path)
    out, in_bullet = [], False
    try:
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    t = re.sub(r"\s+", " ", "".join(s["text"] for s in line["spans"])).strip()
                    if not t:
                        continue
                    if t[0] in "•●▪◦-–":
                        out.append(t.lstrip("•●▪◦-– ").strip())
                        in_bullet = True
                    elif in_bullet and out and t[:1].islower():
                        out[-1] += " " + t
                    else:
                        out.append(t)
                        in_bullet = False
    finally:
        doc.close()
    if not out:
        raise ValueError(f"no text in {os.path.basename(path)}: a scanned PDF can't be read")
    return out


def font_sizes(pdf_path, minimum=None):
    """Every printed text size under `minimum` (default: the layout's min_pt), as {size, text, page}:
    the user's floor (a warning), measured on the PDF."""
    if minimum is None:
        minimum = layout()["min_pt"]
    doc = pymupdf.open(pdf_path)
    small = []
    try:
        for n, page in enumerate(doc):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for s in line["spans"]:
                        if s["text"].strip() and round(s["size"], 2) < minimum - 0.05:
                            small.append({"size": round(s["size"], 2), "text": s["text"].strip()[:60], "page": n + 1})
    finally:
        doc.close()
    return small


DATE_RE = re.compile(r"(19|20)\d\d|present", re.I)
HEADS = {"introduction": "summary", "summary": "summary", "profile": "summary", "education": "education",
         "skills": "skills", "technical skills": "skills", "experience": "experience",
         "professional experience": "experience", "additional experience": "additional",
         "accomplishments & publications": "awards", "awards": "awards", "awards & honors": "awards",
         "accomplishments": "awards", "publications": "publications"}


def parse_cv(name):
    """Best-effort: base CV paragraphs -> editable content. Check the result in tab 3."""
    p = odt_paras(name)
    c = {"name": p[0] if p else "", "contact": [], "summary": "", "skills": [], "experience": [],
         "education": [], "awards": [], "publications": [], "education_first": False}
    if len(p) > 1 and "|" in p[1]:
        parts = [x.strip() for x in p[1].split("|")]
        m = re.search(r"\(\d{3}\).*", parts[0])
        parts[0] = m.group(0) if m else parts[0]
        for x in parts:
            if x.startswith("linkedin") or x.startswith("http"):
                c["contact"].append({"text": x, "href": "https://www." + x if x.startswith("linkedin") else x,
                                     "visible": True})
            else:
                c["contact"].append(x)
    sec, entry, edu = None, None, None
    for t in p[2:]:
        key = HEADS.get(t.strip().lower())
        if key:
            sec = key
            if key == "education":
                c["education_first"] = not c["experience"]
            continue
        if sec == "summary":
            c["summary"] = (c["summary"] + " " + t).strip()
        elif sec == "skills":
            for chunk in re.split(r"(?<=[a-z])(?=[A-Z][A-Za-z ]+\s?:)", t):
                k, _, v = chunk.partition(":")
                if v:
                    c["skills"].append([k.strip(), v.strip()])
        elif sec == "education":
            if re.match(r"(Master|Bachelor|Doctor|Ph\.?D|M\.S|B\.S)", t):
                edu = {"degree": t, "detail": []}
                c["education"].append(edu)
            elif edu is not None:
                edu["detail"].append(t)
        elif sec in ("experience", "additional"):
            if t.endswith(",") or (sec == "additional" and "," in t and t.split(",")[0].isupper()):
                title, _, comp = t.rstrip(",").partition(",")
                entry = {"title": title.strip(), "company": comp.strip(), "dates": "", "bullets": []}
                c["experience"].append(entry)
            elif entry is not None and not entry["company"]:
                entry["company"] = t
            elif entry is not None and not entry["dates"] and DATE_RE.search(t) and len(t) < 40:
                entry["dates"] = t
            elif entry is not None:
                entry["bullets"].append(t)
        elif sec == "awards":
            (c["publications"] if "“" in t or '"' in t else c["awards"]).append(t)
    return c


# ---------- facts (truth check)

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]*|\d[\d,.]*%?")
COMMON = set("""a an and or the of to in on for by with via at as from into over under through while who
which that this these those its it is are was were be been has have had not no nor but each every all
both one two three four five six seven eight nine ten first new using used use across before after
during within up out per than then so such their his her our your my we i you they them also more most
very can will would should may including include includes included present
january february march april may june july august september october november december""".split())


def _norm(w):
    return w.lower().strip(".,:/-")


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def confirmed():
    return _load_json(FACTS, {"words": [], "phrases": [], "notes": []})


def save_confirmed(d):
    os.makedirs(os.path.dirname(FACTS), exist_ok=True)
    with open(FACTS, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


_corpus = None


def corpus():
    """All base CV text (every <cv_prefix>* .pdf, .odt and .docx in the CV folder), lowercased, plus the set of its words."""
    global _corpus
    if _corpus is None:
        text = []
        for d, _, files in os.walk(CV_DIR):  # older CVs in subfolders hold facts too
            for n in files:
                if n.startswith(CV_PREFIX) and n.lower().endswith(CV_TYPES):
                    try:
                        text.extend(odt_paras(os.path.join(d, n)))
                    except Exception:  # noqa: BLE001 - an unreadable CV just adds nothing
                        pass
        low = "\n".join(text).lower()
        _corpus = (low, {_norm(w) for w in WORD_RE.findall(low)})
    return _corpus


def known(w):
    w = _norm(w)
    if not w or w in COMMON:
        return True
    facts = confirmed()
    # the confirmed words, and each word of the confirmed phrases ("modular", "system design"); never the
    # facts' notes or a job's notes: those also say what NOT to claim ("never claim AWS", "no MuJoCo")
    words = corpus()[1] | {_norm(x) for x in facts.get("words", [])} | {
        _norm(p) for x in facts.get("phrases", []) for p in WORD_RE.findall(x.lower())}
    if w in words:
        return True
    if "-" in w and all(known(p) for p in w.split("-") if p):  # "sim-to-real": every part is known
        return True
    for suf in ("s", "es", "ed", "d", "ing", "ly"):
        if w.endswith(suf) and w[: -len(suf)] in words:
            return True
    return any(x.startswith(w[:6]) for x in words) if len(w) >= 8 and not w[0].isdigit() else False


def content_lines(c):
    out = [("Summary", c.get("summary", ""))]
    out += [(f"Skills: {k}", v) for k, v in c.get("skills", [])]
    for e in c.get("experience", []):
        out.append((e.get("company", ""), f"{e.get('title', '')} {e.get('dates', '')}"))
        out += [(e.get("company", ""), b) for b in e.get("bullets", [])]
    for ed in c.get("education", []):
        out.append(("Education", ed.get("degree", "") + " " + " ".join(ed.get("detail", []))))
    out += [("Awards", x) for x in c.get("awards", [])]
    out += [("Publications", x) for x in c.get("publications", [])]
    return out


def declined():
    return [x.lower() for x in confirmed().get("declined", [])]


def is_declined(t):
    """A declined phrase, or a term holding one. declined_terms (keyword status only, not the truth
    check) adds single words the user doesn't want counted as backed, like "pipelines"."""
    t = t.lower()
    if t in [x.lower() for x in confirmed().get("declined_terms", [])]:
        return True
    return any(t == d or re.search(r"(?<![a-z0-9])" + re.escape(d) + r"(?![a-z0-9])", t) for d in declined())


def term_status(t):
    t = t.lower()
    if is_declined(t):
        return "declined"
    if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", corpus()[0]):
        return "backed"
    conf = [p.lower() for p in confirmed()["phrases"]] + [w.lower() for w in confirmed()["words"]]
    return "confirmed" if t in conf else "not on CVs"


def truth_check(c):
    """Words and numbers on the page that no base CV and no confirmed fact backs, and declined terms."""
    flags = []
    for where, line in content_lines(c):
        unknown = sorted({w for w in WORD_RE.findall(line) if not known(w)}, key=str.lower)
        unknown += [f"DECLINED: {d}" for d in declined()
                    if re.search(r"(?<![a-z0-9])" + re.escape(d) + r"(?![a-z0-9])", line.lower())]
        if unknown:
            flags.append({"where": where, "line": line, "words": unknown})
    return flags


# ---------- JD key terms

STOP = COMMON | set("""you'll we're our team role work working job company experience years year ability
strong excellent good great plus preferred required requirements responsibilities qualifications skills
knowledge understanding etc help build building make looking candidate ideal opportunity join including
about other well what how why where when must based related support environment new across engineers
employment applicants applicant benefits salary pay equal status law position candidates people time
day days week weeks hire hiring apply""".split())
# Common JD words that are never keywords (the user's rule: "gm", "test" and the like must not count)
GENERIC = set("""test tests team teams drive drives driven technical technology technologies solutions solution
products product business customers customer world future mission impact passion passionate values culture
growth opportunities global industry leading leader leaders field fields life best high highly level levels
range ranges complex scale real fast part parts set sets way ways area areas needs need want like get using
ensure develop developing deliver delivering provide providing create creating drive enable enabling grow
partner partners including within multiple various key core large small full end ideas problem problems
location locations remote hybrid onsite office relocation travel visa sponsorship us usa united states
benefits bonus compensation insurance holidays vacation paid leave health dental vision
familiarity proficiency proficient ability abilities platform platforms working hands-on large-scale
bs ms ba phd degree degrees equivalent""".split())
# Section headings: required qualifications count double, preferred 1.5x, company and benefit text not at all
SEC_RE = [(re.compile(r"preferred|nice to have|bonus points|good to have|pluses|desired|competitive edge|stand out", re.I), 1.5),  # before "qualifications"
          (re.compile(r"about (us|the company|the organi[sz]ation|the team|gm|general motors)|benefits|compensation|salary|pay range|equal (employment|opportunity)|eeo|why join|perks|diversity|accommodation", re.I), 0.0),
          (re.compile(r"(minimum|basic|required)\s+(qualifications|requirements|skills)|requirements|what you.{0,3}ll need|what you will need|you (have|bring)|must have|qualifications|skills (&|and) abilities|your skills|who you are", re.I), 2.0),
          (re.compile(r"responsibilit|what you.{0,3}ll do|what you will do|the role|about the (role|job)|your impact|day to day", re.I), 1.0)]
TECH = set("""c c++ c# python java javascript typescript go rust sql nosql linux unix windows git docker kubernetes
aws gcp azure cloud react node api apis rest grpc ros cuda opengl vulkan directx unity unreal webgl webgpu glb gltf
simulation simulations rendering graphics 3d physics robotics autonomy autonomous adas perception lidar radar
ml ai machine learning deep vision computer distributed microservices backend frontend performance optimization
testing ci cd devops pipelines infrastructure postgresql bigquery redshift spark kafka matlab embedded realtime
multithreading concurrency algorithms streaming networking security""".split())


def _jd_lines(jd):
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr|ul)>", "\n", jd or "")
    t = html.unescape(html.unescape(re.sub(r"<[^>]+>", " ", t))).replace("\xa0", " ")
    return [l.strip() for l in t.splitlines() if l.strip()]


def jd_terms(jd, role="", company=""):
    """Core JD keywords, ranked. weight = sum over each place the term appears of its section factor
    (required 2, preferred 1.5, other 1, about-company and benefits 0), +3 if it's in the job title,
    then x1.5 if it looks like a skill, tool or domain term. Common words and the company name are skipped."""
    stop = STOP | GENERIC | {w.lower() for w in re.findall(r"[A-Za-z0-9]+", company or "")}
    stop |= {"gm", "general", "motors"} if re.search(r"\bgm\b|general motors", company or "", re.I) else set()
    tokens_of = lambda s: [t.strip(".-") for t in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]*", s)]
    weight, count, places, special = {}, {}, {}, set()
    sec_factor, sec_name = 1.0, "other"

    def add(term, f, where):
        count[term] = count.get(term, 0) + 1
        weight[term] = weight.get(term, 0) + f
        places.setdefault(term, set()).add(where)

    for line in _jd_lines(jd):
        if len(line) < 70 and (line.endswith(":") or len(line.split()) <= 8):  # a section heading
            for rx, f in SEC_RE:
                if rx.search(line):
                    sec_factor, sec_name = f, {2.0: "required", 1.5: "preferred", 1.0: "other", 0.0: "skipped"}[f]
                    break
        if sec_factor == 0:
            continue
        toks = tokens_of(line)
        for i, t in enumerate(toks):
            lo = t.lower()
            if len(t) < 2 or lo in stop:
                continue
            add(lo, sec_factor, sec_name)
            if any(ch.isupper() for ch in t[1:]) or any(ch in t for ch in "+#"):
                special.add(lo)  # C++, PostgreSQL, ROS ...
            if i + 1 < len(toks) and len(toks[i + 1]) > 1 and toks[i + 1].lower() not in stop:
                add(lo + " " + toks[i + 1].lower(), sec_factor, sec_name)
    title = {t.lower() for t in tokens_of(role or "")}
    title_low = (role or "").lower()
    terms = []
    for t, w in weight.items():
        parts = t.split()
        if count[t] < 2 and t not in special and "required" not in places[t] and t not in title_low:
            continue
        if len(parts) == 2 and count[t] < 2 and not all(p in TECH for p in parts):
            continue  # a two-word term must repeat, unless both words are tech words
        if t in title_low or (len(parts) == 1 and t in title):
            w += 3
        if t in special or all(p in TECH for p in parts):
            w *= 1.5
        terms.append({"term": t, "count": count[t], "weight": round(w, 1), "where": sorted(places[t]),
                      "title": t in title_low, "status": term_status(t)})
    # a single word that only shows up inside a kept two-word term adds nothing: drop it
    pairs = {x["term"]: x["count"] for x in terms if " " in x["term"]}
    terms = [x for x in terms if " " in x["term"]
             or x["count"] > sum(n for p, n in pairs.items() if x["term"] in p.split())]
    terms.sort(key=lambda x: (-x["weight"], x["term"]))
    for i, x in enumerate(terms[:30]):
        x["rank"] = i + 1
    return terms[:30]


def mark_terms(terms, c):
    """Add in_cv (exact word, like Rezi) to each ranked term for the CV content c."""
    text = _flat("\n".join(l for _, l in content_lines(c))) if c else None
    for t in terms:
        t["in_cv"] = None if text is None else bool(
            re.search(r"(?<![a-z0-9])" + re.escape(t["term"]) + r"(?![a-z0-9])", text))
    return terms


# ---------- render and check

def fill(text, lay=None):
    """A bullet's share of the line at the layout's body size and text width (over 1.0 wraps)."""
    lay = lay or layout()
    return font().text_length("• " + text, fontsize=lay["body_pt"]) / text_width(lay)


def lint(c):
    out = []
    for where, line in content_lines(c):
        if ";" in line:
            out.append({"where": where, "line": line, "msg": "semicolon"})
        for m in re.finditer(r"\(([^)]*)\)", line):
            if not re.fullmatch(r"\d{3}|[A-Z0-9&]{2,8}", m.group(1)):
                out.append({"where": where, "line": line, "msg": f"parentheses: ({m.group(1)})"})
    lay = layout()
    for e in c.get("experience", []):
        for b in e.get("bullets", []):
            r = fill(b, lay)
            if r > 1.0:
                out.append({"where": e.get("company", ""), "line": b, "msg": f"wraps to 2 lines ({r:.2f}): OK only for a JD keyword or strong fact, on one page"})
    return out


def fills(c):
    lay = layout()
    return [{"e": j, "i": i, "fill": round(fill(b, lay), 3)}
            for j, e in enumerate(c.get("experience", [])) for i, b in enumerate(e.get("bullets", []))]


def render(c, embed_font=False):
    if embed_font:
        src = "data:font/ttf;base64," + base64.b64encode(open(FONT, "rb").read()).decode()
    else:
        src = "/assets/SourceSans3-VF.ttf"
    lay = layout()  # read at every render: a settings change shows in the next print, no restart
    lh, body, gap, bw = lay["line_height"], lay["body_pt"], lay["entry_gap_pt"], lay["bold_weight"]
    pw, ph = page_size(lay)
    ink = lay["text_color"]
    hang = font().text_length("• ", fontsize=body)  # a wrapped bullet's second line starts under its text
    css = f"""
@font-face {{ font-family: 'SSP'; src: url({src}) format('truetype'); font-weight: 200 900; }}
@page {{ size: {pw:g}pt {ph:g}pt; margin: {lay['margin_top_pt']:g}pt {lay['margin_side_pt']:g}pt; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: 'SSP'; color: {ink}; font-size: {body:g}pt; line-height: {lh:g}; }}
h1 {{ font-size: {lay['name_pt']:g}pt; font-weight: {bw}; text-align: center; margin: 0 0 2pt; line-height: {lh:g}; }}
.contact {{ text-align: center; font-size: {body:g}pt; margin-bottom: {lay['header_gap_pt']:g}pt; }}
.contact span + span::before {{ content: "  •  "; white-space: pre; }}
h2 {{ font-size: {lay['heading_pt']:g}pt; font-weight: {bw}; margin: {lay['section_before_pt']:g}pt 0 {lay['section_after_pt']:g}pt;
  padding-bottom: 1pt; border-bottom: {lay['heading_rule_pt']:g}pt solid {ink}; line-height: {lh:g}; }}
p {{ margin: 0; }}
a {{ color: inherit; text-decoration: none; }}
a.vis {{ color: {lay['link_color']}; text-decoration: underline; text-decoration-thickness: 0.4pt; text-underline-offset: 1pt; }}
.sum {{ line-height: {lh:g}; }}
.skill {{ margin: 0 0 {lay['skill_gap_pt']:g}pt; line-height: {lh:g}; }}
.entry {{ margin-bottom: {gap:g}pt; }}
.entry.tight {{ margin-bottom: {gap * 0.55:g}pt; }}
.title {{ font-size: {body:g}pt; font-weight: {bw}; line-height: {lh:g}; }}
.row {{ display: flex; justify-content: space-between; font-weight: {bw}; line-height: {lh:g}; }}
.b {{ line-height: {lh:g}; padding-left: {hang:.2f}pt; text-indent: -{hang:.2f}pt; }}
.b.over {{ background: #fde2e2; }}
.edu {{ margin-bottom: {lay['degree_gap_pt']:g}pt; }}
.edu .deg {{ font-size: {body:g}pt; font-weight: {bw}; line-height: {lh:g}; }}
.edu .det span + span::before {{ content: "  •  "; white-space: pre; }}
.aw {{ font-size: {body:g}pt; font-weight: {bw}; line-height: {lh:g}; margin-bottom: {lay['award_gap_pt']:g}pt; }}
"""
    h = [f"<!doctype html><html><head><meta charset='utf-8'><title>{E(c.get('name', ''))}</title>"
         f"<style>{css}</style></head><body><div id='page'>"]
    h.append(f"<h1>{E(c.get('name', ''))}</h1>")

    def contact_item(x):
        if isinstance(x, dict):
            cls = " class='vis'" if x.get("visible") else ""
            return f"<span><a{cls} href='{E(x.get('href', ''))}'>{E(x.get('text', ''))}</a></span>"
        return f"<span>{E(x)}</span>"

    h.append("<div class='contact'>" + "".join(contact_item(x) for x in c.get("contact", [])) + "</div>")
    h.append(f"<h2>SUMMARY</h2><p class='sum'>{E(c.get('summary', ''))}</p>")
    h.append("<h2>SKILLS</h2>")
    for k, v in c.get("skills", []):
        h.append(f"<p class='skill'>{E(k)}: {E(v)}</p>")

    def education():
        h.append("<h2>EDUCATION</h2>")
        for ed in c.get("education", []):
            h.append(f"<div class='edu'><div class='deg'>{E(ed.get('degree', ''))}</div><div class='det'>"
                     + "".join(f"<span>{E(x)}</span>" for x in ed.get("detail", [])) + "</div></div>")

    if c.get("education_first"):
        education()
    h.append("<h2>EXPERIENCE</h2>")
    for e in c.get("experience", []):
        cls = "entry" if e.get("bullets") else "entry tight"
        h.append(f"<div class='{cls}'><div class='title'>{E(e.get('title', ''))}</div>")
        h.append(f"<div class='row'><span>{E(e.get('company', ''))}</span><span>{E(e.get('dates', ''))}</span></div>")
        for b in e.get("bullets", []):
            over = " over" if not embed_font and fill(b, lay) > 1.0 else ""
            h.append(f"<div class='b{over}'>• {E(b)}</div>")
        h.append("</div>")
    if not c.get("education_first"):
        education()
    if c.get("awards"):
        h.append("<h2>AWARDS &amp; HONORS</h2>" + "".join(f"<p class='aw'>{E(x)}</p>" for x in c["awards"]))
    if c.get("publications"):
        h.append("<h2>PUBLICATIONS</h2>" + "".join(f"<p class='aw'>{E(x)}</p>" for x in c["publications"]))
    h.append("</div></body></html>")
    return "\n".join(h)


# ---------- jobs

def _slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40] or "Job"


def list_jobs():
    out = []
    for d in sorted(os.listdir(JOBS), reverse=True):
        j = _load_json(os.path.join(JOBS, d, "job.json"), None)
        if j:
            out.append({"id": d, "company": j.get("company", ""), "role": j.get("role", "")})
    return out


def new_job(company, role):
    jid = f"{datetime.date.today().isoformat()}_{_slug(company)}"
    base, n = jid, 2
    while os.path.exists(os.path.join(JOBS, jid)):
        jid, n = f"{base}_{n}", n + 1
    os.makedirs(os.path.join(JOBS, jid))
    job = {"id": jid, "company": company, "role": role, "jd": "", "base_cv": "", "content": None,
           "versions": [], "rounds": [], "created": datetime.datetime.now().isoformat(timespec="seconds")}
    save_job(job)
    return job


def job_dir(jid):
    d = os.path.join(JOBS, os.path.basename(jid))
    if not os.path.isdir(d):
        raise FileNotFoundError(jid)
    return d


def load_job(jid):
    return _load_json(os.path.join(job_dir(jid), "job.json"), None)


def save_job(job):
    path = os.path.join(JOBS, os.path.basename(job["id"]), "job.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def export_pdf(job):
    """Print the job's content to a new <cv_prefix><Company>_vN.pdf. Never overwrites."""
    d = job_dir(job["id"])
    n = len(job.get("versions", [])) + 1
    stem = f"{CV_PREFIX}{_slug(job['company'])}_v{n}"
    while os.path.exists(os.path.join(d, stem + ".pdf")):
        n += 1
        stem = f"{CV_PREFIX}{_slug(job['company'])}_v{n}"
    html_path, pdf_path = os.path.join(d, stem + ".html"), os.path.join(d, stem + ".pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render(job["content"], embed_font=True))
    with open(os.path.join(d, stem + ".json"), "w", encoding="utf-8") as f:
        json.dump(job["content"], f, ensure_ascii=False, indent=2)
    prof = os.path.join(ROOT, ".chrome_print")
    url = "file:///" + html_path.replace("\\", "/")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", url],
                   check=True, capture_output=True, timeout=120)
    doc = pymupdf.open(pdf_path)
    pages = len(doc)
    doc.close()
    v = {"file": pdf_path, "pages": pages, "at": datetime.datetime.now().isoformat(timespec="seconds")}
    job.setdefault("versions", []).append(v)
    save_job(job)
    return v


# ---------- Internal ATS score (estimate): exact-word keywords + PDF parse check

def _flat(s):
    s = s.replace("–", "-").replace("—", "-").replace("’", "'").replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_checks(pdf_path, c):
    """Read a PDF back and check it holds the CV: one page, headings, contact, job titles, bullets."""
    doc = pymupdf.open(pdf_path)
    pdf = _flat(" ".join(p.get_text() for p in doc))
    pages = len(doc)
    doc.close()
    checks = [(f"one page (it has {pages})", pages == 1)]
    for h in ["SUMMARY", "SKILLS", "EXPERIENCE", "EDUCATION"]:
        checks.append((f"heading {h}", h.lower() in pdf))
    for x in c.get("contact", []):
        t = x["text"] if isinstance(x, dict) else x
        checks.append((f"contact {t}", _flat(t) in pdf))
    for e in c.get("experience", []):
        checks.append((f"job {e.get('title', '')}", _flat(e.get("title", "")) in pdf))
        for b in e.get("bullets", []):
            checks.append((f"bullet: {b[:50]}", _flat(b) in pdf))
    return checks


def internal_score(job):
    c = job["content"]
    ignored = set(job.get("ignored_terms", []))
    ranked = mark_terms(jd_terms(job.get("jd", ""), job.get("role", ""), job.get("company", "")), c)
    terms = [t for t in ranked if t["term"] not in ignored and t["status"] != "declined"]
    matched, missing, got, total = [], [], 0, 0
    for t in terms:  # weighted by rank weight: a missed top term costs more than a minor one
        total += t["weight"]
        if t["in_cv"]:
            matched.append(t["term"])
            got += t["weight"]
        else:
            missing.append(t)
    kw = round(100 * got / total) if total else 0
    backed = [t["term"] for t in missing if t["status"] in ("backed", "confirmed")]
    not_backed = [t["term"] for t in missing if t["status"] not in ("backed", "confirmed")]
    not_backed += [t["term"] for t in ranked if t["status"] == "declined" and not t["in_cv"]]
    notes, cats = [], {"Keywords": kw}
    versions = job.get("versions", [])
    if versions and os.path.exists(versions[-1]["file"]):
        checks = parse_checks(versions[-1]["file"], c)
        ok = sum(1 for _, v in checks if v)
        cats["Parse"] = round(100 * ok / len(checks))
        notes += [f"Not read back from the PDF: {n}" for n, v in checks if not v][:8]
        notes.append(f"Parse check on {os.path.basename(versions[-1]['file'])}: {ok} of {len(checks)} items read back")
        score = round(0.7 * kw + 0.3 * cats["Parse"])
        if versions[-1]["at"] < job.get("content_saved_at", ""):
            notes.append("The CV changed after this PDF: export again for an up-to-date parse check")
    else:
        score = kw
        notes.append("No PDF exported yet, so this is the keyword part only")
    words = len(c.get("summary", "").split())
    if not 45 <= words <= 75:
        notes.append(f"Summary is {words} words. Rezi likes about 60")
    if versions and os.path.exists(versions[-1]["file"]):
        small = font_sizes(versions[-1]["file"])
        if small:
            notes.append(f"{len(small)} text pieces print under {layout()['min_pt']:g} pt (e.g. {small[0]['size']} pt: "
                         f"{small[0]['text']}). Shorten the wording or ask; never shrink")
    return {"tool": "Internal", "score": score, "categories": cats, "matched": matched,
            "missing_backed": backed, "missing_not_backed": not_backed, "notes": notes, "ranked": ranked}


def save_snapshot(jid, n, data_url):
    m = re.match(r"data:image/(png|jpeg);base64,(.*)", data_url, re.S)
    if not m:
        raise ValueError("not a png or jpeg image")
    name = f"round_{int(n)}_snapshot.{'png' if m.group(1) == 'png' else 'jpg'}"
    with open(os.path.join(job_dir(jid), name), "wb") as f:
        f.write(base64.b64decode(m.group(2)))
    return {"file": name}


# ---------- base CV upload (drag and drop or file button) and job requests from outside

def _copy_cv_into(jid, filename, data):
    name = os.path.basename(filename)
    if not name.lower().endswith(CV_TYPES):
        raise ValueError("a base CV must be .pdf, .odt or .docx")
    path = os.path.join(job_dir(jid), name)
    with open(path, "wb") as f:
        f.write(data)
    odt_paras(path)  # fails here if it isn't a readable CV
    return path


def upload_cv(jid, filename, b64):
    """Store a dropped or chosen CV file in the job folder and make it the job's base CV."""
    path = _copy_cv_into(jid, filename, base64.b64decode(b64.split(",", 1)[-1]))
    job = load_job(jid)
    job["base_cv"] = path
    save_job(job)
    return {"base_cv": path, "paras": odt_paras(path)}


def _jd_from_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        t = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        t = raw.decode("cp1252", errors="replace")
    if path.lower().endswith((".html", ".htm")):
        t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
        t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr)>", "\n", t)
        t = html.unescape(re.sub(r"<[^>]+>", " ", t))
        t = "\n".join(re.sub(r"[ \t\xa0]+", " ", l).strip() for l in t.splitlines())
        t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def import_request(req):
    """Make a job from an outside request. Keys: company, role, jd_text or jd_file, base_cv (path),
    optional content (a dict, e.g. read by the cv module's PDF reader) or content_file, tool (Internal or
    Rezi; none = the app waits for the user's pick), rezi_resume, jd_url, degree_first, notes, work_dir."""
    company = str(req.get("company", "")).strip()
    if not company:
        raise ValueError("the request needs a company")
    jd = req.get("jd_text") or (_jd_from_file(req["jd_file"]) if req.get("jd_file") else "")
    job = new_job(company, str(req.get("role", "")).strip())
    try:
        job["jd"] = jd
        for k in ("jd_url", "rezi_resume", "notes", "work_dir"):
            if req.get(k):
                job[k] = req[k]
        if req.get("tool") in ("Internal", "Rezi"):
            job["tool"] = req["tool"]
        cv = req.get("base_cv")
        if cv:
            if not os.path.isfile(cv):
                raise FileNotFoundError(f"base CV not found: {cv}")
            if _inside(cv, CV_DIR):
                odt_paras(cv)
                job["base_cv"] = os.path.abspath(cv)
            else:  # keep a copy, so the job never depends on a file outside
                with open(cv, "rb") as f:
                    job["base_cv"] = _copy_cv_into(job["id"], cv, f.read())
        if isinstance(req.get("content"), dict) and req["content"].get("experience"):
            job["content"] = req["content"]
            job["content"].setdefault("education_first", False)
        elif req.get("content_file"):
            with open(req["content_file"], encoding="utf-8") as f:
                job["content"] = json.load(f)
            job["content"].setdefault("education_first", False)
        elif job.get("base_cv"):
            job["content"] = parse_cv(job["base_cv"])
        if job.get("content") and "degree_first" in req:
            job["content"]["education_first"] = bool(req["degree_first"])
        job["source"] = req.get("source", "outside request")
        job["content_saved_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        save_job(job)
    except Exception:
        import shutil
        shutil.rmtree(job_dir(job["id"]), ignore_errors=True)  # no half-made jobs
        raise
    return job


def process_inbox():
    """Import every request in inbox\\*.json. Done ones go to inbox\\done (with job_id added),
    failed ones to inbox\\failed with an .error.txt next to them."""
    os.makedirs(INBOX, exist_ok=True)
    made = []
    for n in sorted(os.listdir(INBOX)):
        src = os.path.join(INBOX, n)
        if not (n.lower().endswith(".json") and os.path.isfile(src)):
            continue
        try:
            with open(src, encoding="utf-8-sig") as f:
                req = json.load(f)
            job = import_request(req)
            req["job_id"] = job["id"]
            dest = os.path.join(INBOX, "done")
            os.makedirs(dest, exist_ok=True)
            with open(os.path.join(dest, n), "w", encoding="utf-8") as f:
                json.dump(req, f, ensure_ascii=False, indent=2)
            os.remove(src)
            made.append({"id": job["id"], "company": job["company"], "role": job["role"]})
        except Exception as e:
            dest = os.path.join(INBOX, "failed")
            os.makedirs(dest, exist_ok=True)
            os.replace(src, os.path.join(dest, n))
            with open(os.path.join(dest, n + ".error.txt"), "w", encoding="utf-8") as f:
                f.write(f"{type(e).__name__}: {e}\n")
    return made


# ---------- Rezi score text (pasted)

CATS = ["Content", "Format", "Optimization", "Best Practices", "Application Ready"]


def split_list(s):
    return [x.strip(" •-\t") for x in re.split(r"[\n,]", s or "") if x.strip(" •-\t")]


def parse_score(panel, matched_text, missing_text):
    score = None
    m = re.search(r"Rezi Score\D{0,40}?(\d{1,3})", panel or "", re.I) or re.search(r"\b(\d{1,3})\s*/\s*100", panel or "")
    if m and int(m.group(1)) <= 100:
        score = int(m.group(1))
    cats = {}
    for cat in CATS:
        m = re.search(re.escape(cat) + r"\D{0,20}?(\d{1,3})", panel or "", re.I)
        if m and int(m.group(1)) <= 100:
            cats[cat] = int(m.group(1))
    backed, not_backed = [], []
    for k in split_list(missing_text):
        (backed if term_status(k) in ("backed", "confirmed") else not_backed).append(k)
    return {"score": score, "categories": cats, "matched": split_list(matched_text),
            "missing_backed": backed, "missing_not_backed": not_backed}


# ---------- "Draft from score"
# Internal: proposals built only from the ranked JD terms and the CV's own facts. Nothing is applied
# here: the page shows each proposal and the user ticks what goes in. No writer, no new claims.

def _jd_case(term, jd):
    """The term as the JD spells it (Rezi matches the JD's exact word)."""
    m = re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", "\n".join(_jd_lines(jd)), re.I)
    return m.group(0) if m else term


def _term_in(term, text):
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", _flat(text)))


def _skill_line_for(term, skills):
    """Best Skills line for a new term: the line sharing the most words with it as a tech or soft term."""
    tech = term.lower() in TECH or all(p in TECH for p in term.lower().split())
    best, best_n = len(skills) - 1, -1
    for i, (label, text) in enumerate(skills):
        items = [x.strip().lower() for x in text.split(",")]
        n = sum(1 for x in items if (x in TECH or all(p in TECH for p in x.split())) == tech)
        if re.search(r"practice|method|soft|leader|collab|process|other", label, re.I) and not tech:
            n += 5
        if n > best_n:
            best, best_n = i, n
    return max(best, 0)


def draft_internal(job):
    """Proposals for a first or next draft: Skills items reordered by JD rank (same facts, new order),
    backed JD terms to add with the JD's exact word, and terms the user must confirm before they go in."""
    c = job.get("content") or (parse_cv(job["base_cv"]) if job.get("base_cv") else None)
    if not c:
        raise ValueError("no CV yet: drop a base CV in Job & CV")
    if not job.get("jd"):
        raise ValueError("paste the JD in Job & CV first")
    ignored = set(job.get("ignored_terms", []))
    ranked = [t for t in mark_terms(jd_terms(job["jd"], job.get("role", ""), job.get("company", "")), c)
              if t["term"] not in ignored]
    rank = {t["term"]: t["rank"] for t in ranked}

    def item_rank(item):
        hits = [r for t, r in rank.items() if _term_in(t, item)]
        return min(hits) if hits else 999

    reorder = []
    for i, (label, text) in enumerate(c.get("skills", [])):
        items = [x.strip() for x in text.split(",")]
        new = sorted(items, key=item_rank)  # stable: unranked items keep their order
        if new != items:
            reorder.append({"line": i, "label": label, "before": text, "after": ", ".join(new)})
    skills = c.get("skills", []) or [["Skills", ""]]
    add, ask, declined_out = [], [], []
    for t in ranked:
        if t["in_cv"]:
            continue
        word = _jd_case(t["term"], job["jd"])
        item = {"term": word, "rank": t["rank"], "line": _skill_line_for(word, skills), "status": t["status"]}
        if t["status"] in ("backed", "confirmed"):
            add.append(item)
        elif t["status"] == "declined":
            declined_out.append(word)
        else:
            ask.append(item)
    return {"content": c, "reorder": reorder, "add": add, "ask": ask, "declined": declined_out,
            "skills_labels": [s[0] for s in skills], "matched": [t["term"] for t in ranked if t["in_cv"]]}


# Rezi: the app never touches Rezi. It writes a request for cv_agent, which puts the text into the
# job's Rezi resume and reads back the Rezi Score and keywords (score only: no AI writer, chat or
# suggested edits), then writes a result file the app turns into a round.

def apply_internal_draft(job, reorder=True, add=()):
    """The Internal First Draft with no agent (the cv module's cv.tool_draft): the Skills reorder (same
    facts, new order) and the named backed terms from draft_internal's `add` list, then an Internal round.
    A term not on the CVs (draft_internal's `ask`) is never added here: it needs the user's yes in the app."""
    d = draft_internal(job)
    c = json.loads(json.dumps(d["content"]))
    if not c.get("skills"):
        c["skills"] = [["Skills", ""]]
    if reorder:
        for r in d["reorder"]:
            c["skills"][r["line"]][1] = r["after"]
    offered = {a["term"].lower(): a for a in d["add"]}
    unknown = [t for t in add if str(t).lower() not in offered]
    if unknown:
        raise ValueError(f"only draft_internal's backed terms can be added here, not {unknown}; a term not on "
                         "the CVs needs the user's yes in the CV Tool")
    for t in add:
        a, s = offered[str(t).lower()], None
        s = c["skills"][a["line"]]
        s[1] = s[1].rstrip(", ").rstrip() + ", " + a["term"] if s[1].strip() else a["term"]
    job["content"], job["content_saved_at"] = c, _now().isoformat(timespec="seconds")
    _unsubmit(job)
    save_job(job)
    state = internal_round(load_job(job["id"]))
    return {"applied": {"reorder": len(d["reorder"]) if reorder else 0, "added": [str(t) for t in add]},
            "ask": [a["term"] for a in d["ask"]], "declined": d["declined"], "state": state}


def cv_text(c):
    """Plain resume text, in page order, for pasting into Rezi."""
    out = [c.get("name", ""), " | ".join(x["text"] if isinstance(x, dict) else x for x in c.get("contact", [])),
           "", "SUMMARY", c.get("summary", ""), "", "SKILLS"]
    out += [f"{k}: {v}" for k, v in c.get("skills", [])]
    edu = ["", "EDUCATION"] + [ed.get("degree", "") + (" | " + " | ".join(ed.get("detail", [])) if ed.get("detail") else "")
                               for ed in c.get("education", [])]
    if c.get("education_first"):
        out += edu
    out += ["", "EXPERIENCE"]
    for e in c.get("experience", []):
        out.append(f"{e.get('title', '')} | {e.get('company', '')} | {e.get('dates', '')}")
        out += ["• " + b for b in e.get("bullets", [])]
    if not c.get("education_first"):
        out += edu
    if c.get("awards"):
        out += ["", "AWARDS"] + c["awards"]
    if c.get("publications"):
        out += ["", "PUBLICATIONS"] + c["publications"]
    return "\n".join(out).strip()


def rezi_request(job):
    if not job.get("content"):
        raise ValueError("no CV yet: make the first draft first")
    os.makedirs(REZI_RES, exist_ok=True)
    rid = f"{os.path.basename(job['id'])}_{datetime.datetime.now():%Y%m%d-%H%M%S}"
    req = {"request_id": rid, "job_id": job["id"], "company": job.get("company", ""), "role": job.get("role", ""),
           "base_cv": job.get("base_cv", ""),
           "rezi_resume": job.get("rezi_resume", ""), "jd": job.get("jd", ""), "content": job["content"],
           "text": cv_text(job["content"]),
           "rules": "Score only. Put this text into the job's Rezi resume (one cv_agent made), read it back, "
                    "then read the Rezi Score, its categories and the matched and missing keywords. No Rezi AI "
                    "writer, chat or suggested edits. Change no other resume. Add no term the user's CVs don't back. Never download Rezi's PDF: "
                    "return feedback only (score, categories, matched, missing, issues) and the text read back from Rezi, "
                    "in the same shape as content, as 'content'. The local PDF stays the one shown.",
           "result_file": os.path.join(REZI_RES, rid + ".json"),
           "result_keys": {"request_id": rid, "score": 0, "categories": {}, "matched": [], "missing": [], "issues": [],
                           "note": "", "content": "(optional) text read back, as content"},
           "at": datetime.datetime.now().isoformat(timespec="seconds")}
    path = os.path.join(REZI_REQ, rid + ".json")
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(req, f, ensure_ascii=False, indent=2)
    os.replace(path + ".part", path)
    job["rezi_pending"] = rid
    save_job(job)
    return {"request_id": rid, "job_id": job["id"], "at": req["at"], "file": path, "text": req["text"]}


def rezi_results():
    """Turn each result file from cv_agent into a Rezi round on its job. Done files go to results\\done."""
    if not os.path.isdir(REZI_RES):
        return []
    made = []
    for n in sorted(os.listdir(REZI_RES)):
        src = os.path.join(REZI_RES, n)
        if not (n.endswith(".json") and os.path.isfile(src)):
            continue
        dest = os.path.join(REZI_RES, "done")
        os.makedirs(dest, exist_ok=True)
        try:
            with open(src, encoding="utf-8-sig") as f:
                r = json.load(f)
            job = apply_result(r, n[:-5])
            os.replace(src, os.path.join(dest, n))
            made.append({"id": job["id"], "company": job.get("company", ""), "score": r.get("score")})
        except Exception as e:
            os.replace(src, os.path.join(dest, n + ".failed"))
            with open(os.path.join(dest, n + ".error.txt"), "w", encoding="utf-8") as f:
                f.write(f"{type(e).__name__}: {e}\n")
    return made


# ---------- ATS Loop: outside updates, the loop view, the Internal round, Submit

TARGET = 90


def _now():
    return datetime.datetime.now()


def _round_at():
    return _now().strftime("%m/%d/%Y, %I:%M:%S %p")


def _pdf_pages(path):
    doc = pymupdf.open(path)
    n = len(doc)
    doc.close()
    return n


def _copy_pdf_in(job, pdf, tag):
    """Keep a copy of an outside PDF in the job folder; a PDF already there is used in place."""
    import shutil
    d = job_dir(job["id"])
    if os.path.dirname(os.path.abspath(pdf)).lower() == os.path.abspath(d).lower():
        return os.path.abspath(pdf)
    dest = os.path.join(d, f"{CV_PREFIX}{_slug(job['company'])}_{tag}.pdf")
    shutil.copyfile(pdf, dest)
    return dest


def _unsubmit(job):
    """New PDF, score or content after Submit: the hand-over is no longer current."""
    if not job.get("submitted"):
        return
    job["submitted"]["changed"] = True
    d = job_dir(job["id"])
    for f in (os.path.join(d, "ready.flag"), os.path.join(OUTBOX, os.path.basename(job["id"]) + ".json")):
        if os.path.exists(f):
            os.remove(f)
    res = os.path.join(d, "result.json")
    if os.path.exists(res):
        r = _load_json(res, {})
        r["status"] = "changed_since_submit"
        _write_json(res, r)


def _write_json(path, data):
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(path + ".tmp", path)


def apply_result(r, fname):
    """One file from rezi_requests\\results into its job.
    A Rezi result answers a request (request_id, or the file is named after it).
    An agent update names job_id and brings any of: pdf, score, categories, matched, missing, issues, changes, content."""
    if r.get("job_id") and not r.get("request_id"):
        jid, rid, tool = r["job_id"], "upd_" + fname, str(r.get("tool") or "Agent")
    else:
        rid = r.get("request_id") or fname
        with open(os.path.join(REZI_REQ, rid + ".json"), encoding="utf-8") as f:
            jid = json.load(f)["job_id"]
        tool = "Rezi"
    job = load_job(jid)
    rounds = job.setdefault("rounds", [])
    stamp = _now().isoformat(timespec="seconds")
    changes = str(r.get("changes") or "").strip()
    issues = [str(x) for x in r.get("issues", []) if str(x).strip()]
    scored = r.get("score") is not None
    if isinstance(r.get("content"), dict) and r["content"].get("experience"):
        if tool == "Rezi":
            job["rezi_content"] = r["content"]  # Rezi's read-back never replaces the CV by itself
        else:
            job["content"], job["content_saved_at"] = r["content"], stamp  # the agent is the editor
    pdf_dest = ""
    pdf = r.get("pdf")
    rezi_pdf_ignored = bool(pdf) and _is_rezi(tool)
    if rezi_pdf_ignored:  # rule: the ATS loop never uses Rezi's PDF; the local PDF stays current
        pdf = None
    if pdf and os.path.isfile(pdf) and pdf.lower().endswith(".pdf"):
        tag = ("rezi_" if tool == "Rezi" else "") + (f"r{len(rounds) + 1}" if scored else f"draft{len(job.get('versions', [])) + 1}")
        pdf_dest = _copy_pdf_in(job, pdf, tag)
        if not scored:  # a new draft PDF without a score yet
            job.setdefault("versions", []).append({"file": pdf_dest, "pages": _pdf_pages(pdf_dest), "at": stamp,
                                                   "by": tool, "note": changes})
    elif pdf:
        raise FileNotFoundError(f"pdf not found or not a .pdf: {pdf}")
    if scored:
        miss = [str(k) for k in r.get("missing", [])]
        got = [str(k) for k in r.get("matched", [])]
        from_file = None
        if not miss and not got and "rezi" in tool.lower():  # no lists in the result: take the saved ATS data
            f = ats_file_lists(job)
            if f:
                got, miss, from_file = f["matched"], f["missing"], f["file"]
        note = str(r.get("note", "")).strip()
        rnd = {"at": _round_at(), "tool": tool, "version": os.path.basename(pdf_dest) if pdf_dest else "",
               "note": (("cv_agent, score only. " if tool == "Rezi" else "") + note).strip(),
               "score": r.get("score"), "categories": r.get("categories", {}),
               "matched": got, "missing": miss,
               "missing_backed": [k for k in miss if term_status(k) in ("backed", "confirmed")],
               "missing_not_backed": [k for k in miss if term_status(k) not in ("backed", "confirmed")],
               "changes": changes, "issues": issues, "request_id": rid}
        if pdf_dest:
            rnd["pdf"] = pdf_dest
        if from_file:
            rnd["keywords_from"] = from_file
        if rezi_pdf_ignored:
            rnd["rezi_pdf_ignored"] = True
        rounds.append(rnd)
    if changes or issues or pdf_dest:
        job["loop"] = {"changes": changes, "issues": issues, "at": stamp, "by": tool}
    if job.get("rezi_pending") == rid:
        job.pop("rezi_pending")
    _unsubmit(job)
    save_job(job)
    return job


def _is_rezi(tool):
    return "rezi" in str(tool or "").lower()


def current_pdf(job):
    """The newest local PDF of the job: an export, a draft from an agent, or one a non-Rezi round brought.
    Rezi's PDFs (from older rounds) are never shown: the ATS loop never uses Rezi's PDF."""
    c = [(v["file"], v) for v in job.get("versions", [])
         if not _is_rezi(v.get("by")) and "_rezi_" not in os.path.basename(v.get("file", "")).lower()]
    c += [(r["pdf"], r) for r in job.get("rounds", []) if r.get("pdf") and not _is_rezi(r.get("tool"))]
    c = [(f, x) for f, x in c if f and os.path.isfile(f)]
    if not c:
        return None
    f, x = max(c, key=lambda t: os.path.getmtime(t[0]))
    return {"file": f, "name": os.path.basename(f), "mtime": int(os.path.getmtime(f)), "pages": _pdf_pages(f),
            "exported": "versions" in job and x in job["versions"] and not x.get("by"), "at": x.get("at", "")}


# ---------- Rezi's matched and missing keywords, and where the matched ones sit on the PDF

def _items(s):
    return [x.strip().rstrip(".").strip() for x in s.split(",") if x.strip().rstrip(".").strip()]


def ats_file_lists(job):
    """Matched and missing keywords from saved Rezi ATS data: rezi_ats*.json ({matched, missing}) or
    rezi_ats*.md ("Matched (n): a, b." and "- label: a, b." lines under "Missing") in the job's folder,
    or in cv_agent's work folder of the same name. Newest file first. None if there's none."""
    found = []
    for d in (job_dir(job["id"]), os.path.join(AGENT_WORK, os.path.basename(job["id"]))):
        if os.path.isdir(d):
            found += [os.path.join(d, n) for n in os.listdir(d)
                      if n.lower().startswith("rezi_ats") and n.lower().endswith((".json", ".md"))]
    for f in sorted(found, key=os.path.getmtime, reverse=True):
        if f.lower().endswith(".json"):
            d = _load_json(f, {})
            if d.get("matched") or d.get("missing"):
                return {"matched": [str(x) for x in d.get("matched", [])],
                        "missing": [str(x) for x in d.get("missing", [])], "file": f}
            continue
        with open(f, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        matched, missing, part = [], [], None
        for ln in lines:
            m = re.match(r"\s*Matched\s*\(\d+\)\s*:\s*(.+)$", ln)
            if m:
                matched += _items(m.group(1))
                part = None
                continue
            if re.match(r"\s*Missing\s*\(\d+\)\s*:?", ln):
                part = "missing"
                continue
            if ln.startswith("#"):
                part = None
            elif part and ln.startswith("- ") and ":" in ln:  # top-level bullets only, notes are indented
                missing += _items(ln.split(":", 1)[1])
        if matched or missing:
            return {"matched": matched, "missing": missing, "file": f}
    return None


def keyword_status(t):
    """backed (your CVs or a confirmed fact), declined (you said no), or unconfirmed."""
    s = term_status(t)
    return "declined" if s == "declined" else "backed" if s in ("backed", "confirmed") else "unconfirmed"


def _wnorm(w):
    return w.lower().strip(".,;:()[]\"'!?’“”")


def pdf_marks(pdf_file, terms):
    """Where each term sits on each page, word for word (case-insensitive, whole words, may run across lines).
    Boxes are in PDF points. Only reads the PDF, never writes it."""
    toks = [(i, [_wnorm(x) for x in t.split()]) for i, t in enumerate(terms)]
    doc = pymupdf.open(pdf_file)
    pages, hits = [], [0] * len(terms)
    for pg in doc:
        words = [w for w in pg.get_text("words") if _wnorm(w[4])]
        norm = [_wnorm(w[4]) for w in words]
        rects = []
        for i, tk in toks:
            n = len(tk)
            if not n:
                continue
            for k in range(len(norm) - n + 1):
                if norm[k:k + n] == tk:
                    hits[i] += 1
                    rects += [[round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1), i] for w in words[k:k + n]]
        pages.append({"w": round(pg.rect.width, 1), "h": round(pg.rect.height, 1), "rects": rects})
    doc.close()
    return {"pages": pages, "hits": hits}


def keyword_lists(job, pdf=None):
    """The latest Rezi result's matched and missing keywords, else the latest Internal round's (an
    Internal-only job); the saved ATS data if that round has none."""
    rounds = job.get("rounds", [])
    back = range(len(rounds) - 1, -1, -1)
    idx = next((i for i in back if "rezi" in str(rounds[i].get("tool", "")).lower()), None)
    if idx is None:
        idx = next((i for i in back if rounds[i].get("tool") == "Internal"), None)
    r = rounds[idx] if idx is not None else {}
    matched = list(r.get("matched") or [])
    missing = list(r.get("missing") or (r.get("missing_backed", []) + r.get("missing_not_backed", [])))
    kind = "Internal" if r.get("tool") == "Internal" else "Rezi"
    src = f"{kind} round {idx + 1}" + (f" · {r.get('at')}" if r.get("at") else "") if idx is not None else ""
    if r.get("keywords_from"):
        src += " · lists from " + os.path.basename(r["keywords_from"])
    if not matched and not missing:
        f = ats_file_lists(job)
        if not f:
            return None
        matched, missing, src = f["matched"], f["missing"], "saved ATS data: " + os.path.basename(f["file"])
    marks = pdf_marks(pdf["file"], matched) if pdf else {"pages": [], "hits": [0] * len(matched)}
    return {"source": src, "score": r.get("score"),
            "matched": [{"term": t, "hits": h} for t, h in zip(matched, marks["hits"])],
            "missing": [{"term": t, "status": keyword_status(t)} for t in missing],
            "marks": marks["pages"], "pdf": pdf["name"] if pdf else ""}


def render_page_png(pdf_file, n, zoom=2.0):
    """One page as a PNG, in memory, for the on-screen view. The PDF file is not changed."""
    doc = pymupdf.open(pdf_file)
    try:
        return doc[int(n)].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")
    finally:
        doc.close()


def loop_sig(jid):
    return {"sig": os.stat(os.path.join(job_dir(jid), "job.json")).st_mtime_ns}


def _issues(job, pdf, last):
    out = []
    add = lambda kind, text: out.append({"kind": kind, "text": text})
    loop = job.get("loop") or {}
    for s in loop.get("issues") or (last or {}).get("issues", []):
        add("agent", s)
    c = job.get("content") or {}
    if pdf:
        side = os.path.splitext(pdf["file"])[0] + ".json"  # an export keeps its content next to it
        pc = _load_json(side, None) if os.path.exists(side) else c
        checks = parse_checks(pdf["file"], pc or {})
        bad = [n for n, ok in checks if not ok]
        nb = [n for n in bad if n.startswith("bullet:")]
        for n in [n for n in bad if not n.startswith("bullet:")][:5]:
            add("parse", "Not read back from the PDF: " + n)
        if nb:
            nall = sum(1 for n, _ in checks if n.startswith("bullet:"))
            add("parse", f"{len(nb)} of {nall} bullets not read back word for word")
        if pdf["exported"] and pdf["at"] < job.get("content_saved_at", ""):
            add("parse", "The CV changed after this PDF was made")
    if last:
        if last.get("missing_backed"):
            add("missing", "Missing, your CVs back it (worth a true tweak with the JD's word): " + ", ".join(last["missing_backed"][:6]))
        if last.get("missing_not_backed"):
            add("left out", "Missing, not on your CVs or declined (left out unless true for you): " + ", ".join(last["missing_not_backed"][:8]))
        for n in last.get("notes", []):
            if not n.startswith(("Not read back", "Parse check on", "The CV changed")):
                add("note", n)
    if c.get("experience"):
        for t in truth_check(c)[:4]:
            add("truth", f"Not on your CVs ({t['where']}): " + ", ".join(t["words"][:6]))
        for l in lint(c)[:3]:
            add("style", f"{l['msg']} ({l['where']}): {l['line'][:60]}")
    return out


def loop_state(job):
    """What the ATS Loop tab shows: the current PDF, the score, the biggest issues, the change notes, the rounds."""
    rounds = job.get("rounds", [])
    last = rounds[-1] if rounds else None
    pdf = current_pdf(job)
    loop = job.get("loop") or {}
    if loop.get("changes"):
        notes = {"text": loop["changes"], "at": loop.get("at", ""), "by": loop.get("by", "")}
    elif last:
        notes = {"text": last.get("changes") or last.get("note", ""), "at": last.get("at", ""), "by": last.get("tool", "")}
    else:
        notes = {"text": "", "at": "", "by": ""}
    sub = job.get("submitted")
    if sub and pdf and not sub.get("changed") and (sub.get("pdf_mtime") != pdf["mtime"] or sub.get("rounds") != len(rounds)):
        sub = dict(sub, changed=True)
    return {"sig": loop_sig(job["id"])["sig"], "pdf": pdf, "target": TARGET,
            "score": None if not last else {k: last.get(k) for k in ("score", "tool", "categories", "at", "version")} |
            {"matched": len(last.get("matched", [])), "reached": (last.get("score") or 0) >= TARGET},
            "issues": _issues(job, pdf, last), "notes": notes,
            "rounds": [{"n": i + 1, "at": r.get("at", ""), "tool": r.get("tool", ""), "score": r.get("score"),
                        "changes": r.get("changes") or r.get("note", "")} for i, r in enumerate(rounds)],
            "submitted": sub, "pending": job.get("rezi_pending", ""), "keywords": keyword_lists(job, pdf)}


def internal_round(job):
    """Internal mode, one click: export the PDF, score it, save the round."""
    if not job.get("content"):
        raise ValueError("no CV yet: make the First Draft first")
    v = export_pdf(job)
    s = internal_score(job)
    s.pop("ranked", None)
    changes = "PDF made from the current draft and scored with the Internal estimate (not a Rezi Score)."
    job.setdefault("rounds", []).append(s | {"at": _round_at(), "tool": "Internal", "version": os.path.basename(v["file"]),
                                            "pdf": v["file"], "note": "Internal round", "changes": changes, "issues": [],
                                            "request_id": "int_" + _now().strftime("%Y%m%d-%H%M%S")})
    job["loop"] = {"changes": changes, "issues": [], "at": _now().isoformat(timespec="seconds"), "by": "Internal"}
    _unsubmit(job)
    save_job(job)
    return loop_state(job)


SECTION_NAMES = ["summary", "skills", "experience", "education", "awards", "publications"]


def submit(job):
    """The user is satisfied: copy the current PDF as _final.pdf, write result.json (CV_RESULT shape),
    copy it to outbox\\<job_id>.json, and write ready.flag last."""
    import shutil
    pdf = current_pdf(job)
    rounds = job.get("rounds", [])
    if not pdf:
        raise ValueError("no PDF yet: run a round first")
    if not rounds or rounds[-1].get("score") is None:
        raise ValueError("no score yet: score the current PDF first")
    d = job_dir(job["id"])
    _unsubmit(job)  # clear an older hand-over first
    for f in ("ready.flag",):
        if os.path.exists(os.path.join(d, f)):
            os.remove(os.path.join(d, f))
    last = rounds[-1]
    final = os.path.join(d, f"{CV_PREFIX}{_slug(job['company'])}_final.pdf")
    shutil.copyfile(pdf["file"], final)
    min_pt = layout()["min_pt"]
    try:  # a warning only: the user's Submit is never refused for it (2026-11-10)
        small = font_sizes(final, min_pt)
    except Exception as exc:  # noqa: BLE001 - an unreadable PDF still goes through as submitted
        print(f"cv_tool: couldn't measure the text sizes of {final}: {exc}")
        small = []
    c = job.get("content") or {}
    order = [s for s in SECTION_NAMES if c.get(s) or s in ("summary", "skills", "experience", "education")]
    if c.get("education_first") and "education" in order:
        order.remove("education")
        order.insert(order.index("skills") + 1, "education")
    left = [{"term": t, "why": "you declined it" if is_declined(t) else "not on your CVs"} for t in last.get("missing_not_backed", [])]
    state = loop_state(job)
    score = last.get("score")
    now = _now().isoformat(timespec="seconds")
    res_path = os.path.join(d, "result.json")
    result = {
        "status": "ready", "stop_reason": "" if score >= TARGET else f"Submitted by the user below the target of {TARGET}",
        "pdf_path": final, "source_pdf": pdf["file"], "odt_path": "", "report_path": res_path,
        "job_id": job["id"], "company": job.get("company", ""), "role": job.get("role", ""), "tool": last.get("tool", ""),
        "rezi_resume": {"name": job["rezi_resume"]} if job.get("rezi_resume") else None, "check_copy": None,
        "target_score": TARGET, "final_score": score, "final_categories": last.get("categories", {}),
        "rounds": [{"score": r.get("score"), "tool": r.get("tool", ""), "added": [],
                    "missing": r.get("missing_backed", []) + r.get("missing_not_backed", []),
                    "note": r.get("changes") or r.get("note", "")} for r in rounds],
        "matched_keywords": last.get("matched", []),
        "missing_keywords": last.get("missing_backed", []) + last.get("missing_not_backed", []),
        "keywords_left_out": [x["term"] for x in left], "keywords_left_out_why": left,
        "recommendations": ([f"Still missing though your CVs back it: {', '.join(last['missing_backed'])}"] if last.get("missing_backed") else []),
        "change_notes": state["notes"]["text"], "open_issues": [i["text"] for i in state["issues"]],
        "match_ok": None, "compare": None, "one_page": pdf["pages"] == 1,
        "section_order": order,
        "order_reason": "JD asks for a master's, so Education is right under Skills" if c.get("education_first") else "Education stays after Experience",
        "approved_by_user": True, "submitted_at": now, "small_text": small, "min_pt": min_pt}
    _write_json(res_path, result)
    os.makedirs(OUTBOX, exist_ok=True)
    _write_json(os.path.join(OUTBOX, os.path.basename(job["id"]) + ".json"), result)
    with open(os.path.join(d, "ready.flag"), "w", encoding="utf-8") as f:  # written last: result.json is complete
        f.write(json.dumps({"submitted_at": now, "result": res_path, "pdf_path": final}))
    job["submitted"] = {"at": now, "pdf": final, "score": score, "pdf_mtime": pdf["mtime"], "rounds": len(rounds),
                        "changed": False, "small_text": len(small), "min_pt": min_pt}
    save_job(job)
    try:
        archive_older(job)
    except OSError as exc:  # the Submit stands; the old jobs just stay where they are
        print(f"cv_tool: couldn't archive the older jobs of {job['id']}: {exc}")
    return result


def archive_older(job):
    """At a Submit: the other jobs for the same work folder that were never submitted move to
    jobs\\_archive (moved, never deleted). Gives the ids moved."""
    import shutil
    work = job.get("work_dir")
    if not work:
        return []
    same = os.path.normcase(os.path.normpath(work))
    root, moved = os.path.join(JOBS, "_archive"), []
    for d in sorted(os.listdir(JOBS)):
        if d == os.path.basename(job["id"]) or d.startswith("_"):
            continue
        other = _load_json(os.path.join(JOBS, d, "job.json"), None)
        if not other or os.path.normcase(os.path.normpath(other.get("work_dir") or "")) != same:
            continue
        if os.path.exists(os.path.join(JOBS, d, "ready.flag")):
            continue
        os.makedirs(root, exist_ok=True)
        dest, n = os.path.join(root, d), 2
        while os.path.exists(dest):
            dest, n = os.path.join(root, f"{d}_{n}"), n + 1
        shutil.move(os.path.join(JOBS, d), dest)
        moved.append(d)
    return moved


# ---------- the cv module's side (cv.tool_status, cv.tool_round, cv.tool_result): the agent edits, the user submits

ROUND_KEYS = ("score", "categories", "matched", "missing", "issues", "changes", "note", "request_id")


def agent_round(r):
    """One round from cv_agent. `job_id` required. `content` (the app's shape) becomes the job's CV: the agent is
    the editor. `export` (default: true when content is given) prints a new local PDF; an Internal job with no
    score given is scored by the Internal estimate. Score fields (`score, categories, matched, missing, issues,
    changes, note`, and `request_id` when it answers a Rezi request) are saved as a round. Rezi's PDF is never
    taken. Returns the PDF, its text under 10 pt, the loop state and the rules checklist."""
    jid = str(r.get("job_id") or "")
    job = load_job(jid) if jid else None
    if not job:
        raise FileNotFoundError(f"no CV Tool job {jid!r}")
    content = r.get("content")
    if content is not None:
        if not (isinstance(content, dict) and content.get("experience")):
            raise ValueError("content must be the CV in the app's shape, with its experience")
        content.setdefault("education_first", (job.get("content") or {}).get("education_first", False))
        job["content"], job["content_saved_at"] = content, _now().isoformat(timespec="seconds")
        _unsubmit(job)
        save_job(job)
    export = r.get("export", content is not None)
    tool = r.get("tool") or job.get("tool") or ""
    pdf = None
    if export:
        if not job.get("content"):
            raise ValueError("no CV content yet: send content first")
        if tool == "Internal" and r.get("score") is None and not r.get("request_id"):
            internal_round(job)  # export + Internal score, saved as a round
            job = load_job(jid)
            return _round_answer(job, (current_pdf(job) or {}).get("file"))
        pdf = export_pdf(job)["file"]
        job = load_job(jid)
    upd = {k: r[k] for k in ROUND_KEYS if r.get(k) is not None}
    if upd:
        upd["job_id"] = jid
        upd["tool"] = "Rezi" if upd.get("request_id") else (tool or "Agent")
        if upd.get("request_id"):
            upd.pop("job_id")
        job = apply_result(upd, "api_" + _now().strftime("%Y%m%d-%H%M%S"))
        if pdf and upd.get("score") is not None and job.get("rounds"):
            job["rounds"][-1]["version"] = os.path.basename(pdf)
            save_job(job)
    return _round_answer(job, pdf or (current_pdf(job) or {}).get("file"))


def _round_answer(job, pdf):
    return {"job_id": job["id"], "pdf": pdf or "", "small_text": font_sizes(pdf) if pdf and os.path.isfile(pdf) else [],
            "state": loop_state(job), "rules": rules()}


def job_status(jid):
    """What cv_agent needs to work on a job: the pick, the content and its plain text, a pending Rezi
    request, the loop (score, issues, rounds) and whether the user submitted."""
    job = load_job(jid)
    if not job:
        raise FileNotFoundError(f"no CV Tool job {jid!r}")
    pending = None
    if job.get("rezi_pending"):
        req = _load_json(os.path.join(REZI_REQ, job["rezi_pending"] + ".json"), {})
        pending = {"request_id": job["rezi_pending"], "text": req.get("text", ""), "rules": req.get("rules", "")}
    c = job.get("content")
    return {"id": job["id"], "company": job.get("company", ""), "role": job.get("role", ""),
            "tool": job.get("tool", ""), "rezi_resume": job.get("rezi_resume", ""), "content": c,
            "text": cv_text(c) if c else "", "rezi_request": pending, "loop": loop_state(job),
            "ready": os.path.exists(os.path.join(job_dir(jid), "ready.flag"))}


def submitted_jobs():
    """Every job the user submitted (its ready.flag), as {job_id, submitted_at}: the cv module's catch-up
    look on start, for Submits made while it was off."""
    out = []
    for d in sorted(os.listdir(JOBS)) if os.path.isdir(JOBS) else []:
        flag = os.path.join(JOBS, d, "ready.flag")
        if d.startswith("_") or not os.path.exists(flag):
            continue
        job = _load_json(os.path.join(JOBS, d, "job.json"), None)
        if job and job.get("id"):
            out.append({"job_id": job["id"], "submitted_at": (job.get("submitted") or {}).get("at", "")})
    return out


def job_result(jid):
    """The user's Submit: {ready: false} until ready.flag exists, then result.json and its PDF's text under 10 pt."""
    job = load_job(jid)
    if not job:
        raise FileNotFoundError(f"no CV Tool job {jid!r}")
    d = job_dir(jid)
    if not os.path.exists(os.path.join(d, "ready.flag")):
        return {"ready": False, "submitted": job.get("submitted")}
    res = _load_json(os.path.join(d, "result.json"), {})
    pdf = res.get("pdf_path", "")
    return {"ready": True, "result": res, "work_dir": job.get("work_dir", ""),
            "small_text": font_sizes(pdf) if pdf and os.path.isfile(pdf) else []}


configure()  # the defaults; server.main() calls it again with the config's folders
