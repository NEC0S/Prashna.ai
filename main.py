import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
BUILD_DIR = os.environ.get("BUILD_DIR", "/app/build")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(BUILD_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Curated subject library
# ---------------------------------------------------------------------------
# One shared 80-mark, 5-section blueprint (mirrors the standard modern CBSE
# Class 10 board-exam structure: A = MCQ + Assertion-Reason, B = Very Short
# Answer, C = Short Answer, D = Long Answer with internal choice, E =
# Case-based). Subjects differ mainly in *topics*, so the section shape is
# shared and only copied (never mutated) per subject.
def _shared_80_mark_sections() -> List[Dict[str, Any]]:
    return copy.deepcopy([
        {"name": "Section A", "question_type": "MCQ", "num_questions": 18,
         "marks_each": 1, "difficulty": "easy", "internal_choice": False},
        {"name": "Section A (Assertion-Reason)", "question_type": "Assertion-Reason",
         "num_questions": 2, "marks_each": 1, "difficulty": "medium", "internal_choice": False},
        {"name": "Section B", "question_type": "Very Short Answer", "num_questions": 6,
         "marks_each": 2, "difficulty": "medium", "internal_choice": False},
        {"name": "Section C", "question_type": "Short Answer", "num_questions": 7,
         "marks_each": 3, "difficulty": "medium", "internal_choice": False},
        {"name": "Section D", "question_type": "Long Answer", "num_questions": 3,
         "marks_each": 5, "difficulty": "hard", "internal_choice": True},
        {"name": "Section E", "question_type": "Case Study", "num_questions": 3,
         "marks_each": 4, "difficulty": "mixed", "internal_choice": False},
    ])


SUBJECT_LIBRARY: Dict[str, Dict[str, Any]] = {
    "Mathematics": {
        "topics": [
            "Real Numbers", "Polynomials", "Pair of Linear Equations in Two Variables",
            "Quadratic Equations", "Arithmetic Progressions", "Triangles",
            "Coordinate Geometry", "Introduction to Trigonometry",
            "Some Applications of Trigonometry", "Circles", "Areas Related to Circles",
            "Surface Areas and Volumes", "Statistics", "Probability",
        ],
        "sections": _shared_80_mark_sections(),
    },
    "Science": {
        "topics": [
            "Chemical Reactions and Equations", "Acids, Bases and Salts",
            "Metals and Non-metals", "Carbon and its Compounds", "Life Processes",
            "Control and Coordination", "How do Organisms Reproduce?",
            "Heredity and Evolution", "Light - Reflection and Refraction",
            "The Human Eye and the Colourful World", "Electricity",
            "Magnetic Effects of Electric Current", "Our Environment",
            "Management of Natural Resources",
        ],
        "sections": _shared_80_mark_sections(),
    },
    "Social Science": {
        "topics": [
            "The Rise of Nationalism in Europe", "Nationalism in India",
            "The Making of a Global World", "The Age of Industrialisation",
            "Resources and Development", "Forest and Wildlife Resources",
            "Water Resources", "Agriculture", "Minerals and Energy Resources",
            "Manufacturing Industries", "Lifelines of National Economy",
            "Power-Sharing", "Federalism", "Democracy and Diversity",
            "Political Parties", "Outcomes of Democracy", "Development",
            "Sectors of the Indian Economy", "Money and Credit",
            "Globalisation and the Indian Economy",
        ],
        "sections": _shared_80_mark_sections(),
    },
    "English": {
        "topics": [
            "Reading Comprehension (Unseen Passage)", "Grammar - Tenses and Modals",
            "Grammar - Reported Speech and Determiners", "Note-Making and Summarising",
            "Letter/Email Writing", "Analytical Paragraph Writing",
            "First Flight - Prose", "First Flight - Poetry",
            "Footprints Without Feet - Supplementary Reader",
        ],
        "sections": _shared_80_mark_sections(),
    },
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "board": "CBSE",
    "class_name": "10",
    "subject": "Mathematics",
    "duration_minutes": 180,
    "max_marks": 80,
    "model_name": "gemini-3.1-flash-lite",
    "topics": SUBJECT_LIBRARY["Mathematics"]["topics"],
    "sections": SUBJECT_LIBRARY["Mathematics"]["sections"],
}

# In-memory paper registry: {paper_id: {"latex": str, "compiled": bool}}
# A real deployment should replace this with Postgres + S3/Supabase Storage,
# same as the career-agent-saas / ClaimPilot pattern.
PAPERS: Dict[str, Dict[str, Any]] = {}

# In-memory job registry, used to report live progress for the async
# generation endpoint below - same "swap for Postgres later" caveat as
# PAPERS. Each job: {"status": "generating"|"compiling"|"done"|"error",
# "log": [str, ...], "paper_id": str|None, "error": str|None}.
JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _job_create(job_id: str):
    with _JOBS_LOCK:
        JOBS[job_id] = {"status": "generating", "log": [], "paper_id": None, "error": None}


def _job_log(job_id: str, message: str):
    with _JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["log"].append(message)


def _job_set(job_id: str, **kwargs):
    with _JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(kwargs)


def _job_snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


_MODEL_CACHE: Dict[str, Any] = {}


def get_model(model_name: Optional[str] = None):
    """Lazily builds (and caches) a Gemini chat model for the requested
    model_name, so the "Model" dropdown in the frontend actually has an
    effect instead of every request silently using one fixed model."""
    if not GEMINI_API_KEY:
        return None
    name = model_name or DEFAULT_CONFIG["model_name"]
    if name not in _MODEL_CACHE:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _MODEL_CACHE[name] = ChatGoogleGenerativeAI(
            model=name, google_api_key=GEMINI_API_KEY, temperature=0.4
        )
    return _MODEL_CACHE[name]


# ---------------------------------------------------------------------------
# LaTeX helpers
# ---------------------------------------------------------------------------
def build_latex_header(config: Dict[str, Any]) -> str:
    hours = config["duration_minutes"] // 60
    minutes = config["duration_minutes"] % 60
    time_str = f"{hours} Hours" + (f" {minutes} Minutes" if minutes else "")
    return r"""\documentclass[12pt,a4paper]{article}
\usepackage[margin=0.9in]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{tikz}
\usepackage{enumitem}
\usepackage{fancyhdr}
\setlength{\headheight}{15pt}
\pagestyle{fancy}
\fancyhf{}
\lhead{""" + config["board"] + r"""}
\rhead{Class """ + config["class_name"] + r""" -- """ + config["subject"] + r"""}
\cfoot{\thepage}

\begin{document}
\begin{center}
{\Large \textbf{""" + config["subject"].upper() + r"""}}\\[4pt]
Time Allowed: """ + time_str + r""" \hfill Maximum Marks: """ + str(config["max_marks"]) + r"""
\end{center}
\hrule
\vspace{8pt}
"""


LATEX_FOOTER = r"\end{document}"

LATEX_DIAGRAM_TEST_WRAPPER = r"""\documentclass{standalone}
\usepackage{tikz}
\begin{document}
\begin{tikzpicture}
%s
\end{tikzpicture}
\end{document}
"""

LATEX_SAFETY_RULES = """LaTeX formatting rules (violating these breaks the compiled PDF):
- Never write a plain "->" or "-->" for a reaction/process arrow - always use math mode, e.g. $\\rightarrow$.
- Wrap chemical formula subscripts and any exponents in math mode, e.g. $H_2O$, $CO_2$, $x^2$, not H2O or x^2 as bare text.
- Use $^\\circ$C for temperatures/angles in degrees, not a bare degree symbol.
- Escape literal %, &, #, _ characters that are NOT part of LaTeX math or a command (e.g. "10% of the energy" must be written "10\\% of the energy").
- Use standard math mode ($...$) for all equations, formulas, and algebraic expressions."""

ASSERTION_REASON_OPTIONS = [
    "Both A and R are true, and R is the correct explanation of A.",
    "Both A and R are true, but R is not the correct explanation of A.",
    "A is true, but R is false.",
    "A is false, but R is true.",
]


# ---------------------------------------------------------------------------
# Master prompt template (prompt_template.md / .txt)
# ---------------------------------------------------------------------------
# This lets the *methodology* (assessment philosophy, quality bar, LaTeX
# conventions) live in an editable text file instead of being hardcoded in
# Python - edit prompt_template.md and every future generation call picks it
# up automatically, no code change needed. Every {{PLACEHOLDER}} in it is
# filled from the exact same `config` dict the rest of the app already uses,
# so it can never describe a different subject/board/marks setup than what
# actually gets generated.
_PROMPT_TEMPLATE_RAW: Optional[str] = None
_PROMPT_TEMPLATE_LOADED = False
_PROMPT_TEMPLATE_FILENAMES = ("prompt_template.md", "prompt_template.txt")


def _load_prompt_template() -> str:
    global _PROMPT_TEMPLATE_RAW, _PROMPT_TEMPLATE_LOADED
    if _PROMPT_TEMPLATE_LOADED:
        return _PROMPT_TEMPLATE_RAW or ""
    _PROMPT_TEMPLATE_LOADED = True

    base_dir = os.path.dirname(os.path.abspath(__file__))
    for filename in _PROMPT_TEMPLATE_FILENAMES:
        path = os.path.join(base_dir, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            # Strip the leading "HOW TO USE THIS FILE" HTML comment block -
            # that block documents the template for a human editor, it isn't
            # an instruction meant for the model.
            text = re.sub(r"<!--.*?-->", "", text, count=1, flags=re.S)
            _PROMPT_TEMPLATE_RAW = text.strip()
            print(f"Loaded master prompt template from {filename}", flush=True)
            return _PROMPT_TEMPLATE_RAW

    print(
        "No prompt_template.md/.txt found next to main.py - "
        "falling back to a minimal built-in prompt.",
        flush=True,
    )
    _PROMPT_TEMPLATE_RAW = ""
    return _PROMPT_TEMPLATE_RAW


def _difficulty_percentages(config: Dict[str, Any]):
    """Computes the Easy/Moderate/Hard split from the ACTUAL sections the
    teacher configured (marks-weighted), instead of hardcoding the
    template's 25/25/50 default - so the printed difficulty rule always
    matches the paper that's actually generated."""
    buckets = {"easy": 0.0, "moderate": 0.0, "hard": 0.0}
    total = 0
    for s in config.get("sections", []):
        marks = s["num_questions"] * s["marks_each"]
        total += marks
        diff = (s.get("difficulty") or "medium").lower()
        if diff == "easy":
            buckets["easy"] += marks
        elif diff == "hard":
            buckets["hard"] += marks
        elif diff == "mixed":
            third = marks / 3
            buckets["easy"] += third
            buckets["moderate"] += third
            buckets["hard"] += third
        else:  # "medium" or anything unrecognized
            buckets["moderate"] += marks

    if total == 0:
        return 25, 25, 50

    pcts = {k: round(v / total * 100) for k, v in buckets.items()}
    drift = 100 - sum(pcts.values())
    if drift != 0:
        biggest = max(pcts, key=pcts.get)
        pcts[biggest] += drift
    return pcts["easy"], pcts["moderate"], pcts["hard"]


def _marks_distribution_text(config: Dict[str, Any]) -> str:
    parts = []
    for s in config.get("sections", []):
        subtotal = s["num_questions"] * s["marks_each"]
        parts.append(f"{s['name']} ({s['question_type']}): {s['num_questions']} x {s['marks_each']} = {subtotal} marks")
    return "; ".join(parts) if parts else "not specified"


def _section_structure_text(config: Dict[str, Any]) -> str:
    parts = [f"{s['name']}: {s['question_type']} ({s['num_questions']} questions)" for s in config.get("sections", [])]
    return "; ".join(parts) if parts else "not specified"


def _question_types_text(config: Dict[str, Any]) -> str:
    seen: List[str] = []
    for s in config.get("sections", []):
        if s["question_type"] not in seen:
            seen.append(s["question_type"])
    return ", ".join(seen) if seen else "not specified"


def _internal_choice_text(config: Dict[str, Any]) -> str:
    names = [s["name"] for s in config.get("sections", []) if s.get("internal_choice")]
    return f"Internal choice required in: {', '.join(names)}." if names else "No internal choice required."


def build_master_prompt(config: Dict[str, Any]) -> str:
    """Fills prompt_template.md's placeholders from the live paper config.
    Returns "" if no template file is present (callers treat that as
    "skip the master-prompt preamble")."""
    template = _load_prompt_template()
    if not template:
        return ""

    hours = config["duration_minutes"] // 60
    minutes = config["duration_minutes"] % 60
    duration_str = f"{hours} Hours" + (f" {minutes} Minutes" if minutes else "")
    easy_pct, moderate_pct, hard_pct = _difficulty_percentages(config)
    total_q = sum(s["num_questions"] for s in config.get("sections", []))
    subject_slug = str(config.get("subject", "Subject")).replace(" ", "_")

    values = {
        "BOARD": config.get("board", "CBSE"),
        "CLASS": config.get("class_name", "10"),
        "SUBJECT": config.get("subject", "General"),
        "TEST_LABEL": "Question Paper",
        "SCHOOL_NAME": "not specified",
        "CHAPTERS_TOPICS": ", ".join(config.get("topics", [])) or "not specified",
        "TOPIC_WEIGHTAGE": "distribute questions evenly across the listed topics unless one clearly warrants more emphasis",
        "DURATION": duration_str,
        "MAX_MARKS": str(config.get("max_marks", "")),
        "NUM_QUESTIONS": str(total_q),
        "QUESTION_TYPES": _question_types_text(config),
        "MARKS_DISTRIBUTION": _marks_distribution_text(config),
        "SECTION_STRUCTURE": _section_structure_text(config),
        "DIFFICULTY_EASY_PCT": str(easy_pct),
        "DIFFICULTY_MODERATE_PCT": str(moderate_pct),
        "DIFFICULTY_HARD_PCT": str(hard_pct),
        "INTERNAL_CHOICE_RULES": _internal_choice_text(config),
        "SPECIAL_INSTRUCTIONS": "None beyond the rules stated in this document.",
        "OUTPUT_FILENAME": f"Class_{config.get('class_name', 'X')}_{subject_slug}_Question_Paper.tex",
    }

    rendered = template
    for key, val in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(val))
    # Any leftover placeholder (a typo, or a future addition to the template
    # file that this function doesn't know about yet) gets a safe fallback
    # instead of leaking a literal "{{...}}" into the prompt sent to the model.
    rendered = re.sub(r"\{\{[A-Z_]+\}\}", "(not specified)", rendered)
    return rendered


def render_general_instructions(config: Dict[str, Any]) -> str:
    """Builds a numbered General Instructions block from the actual section
    layout, instead of one generic boilerplate sentence - so the printed
    instructions always match the paper that follows."""
    sections = config["sections"]
    total_q = sum(s["num_questions"] for s in sections)
    lines = [
        f"This question paper consists of {total_q} question(s) organised into "
        f"{len(sections)} section(s). All questions are compulsory unless an "
        f"internal choice is indicated."
    ]
    q_num = 1
    for s in sections:
        end = q_num + s["num_questions"] - 1
        choice_note = (
            " An internal choice has been provided in each of these questions."
            if s.get("internal_choice") else ""
        )
        q_range = f"Q.{q_num}" if end == q_num else f"Q.{q_num} to Q.{end}"
        lines.append(
            f"{s['name']} ({q_range}): {s['question_type']} questions carrying "
            f"{s['marks_each']} mark(s) each.{choice_note}"
        )
        q_num = end + 1
    lines.append("Draw neat, labelled diagrams wherever necessary.")
    lines.append(f"This paper follows {config['board']} format and marking conventions.")

    out = [r"\textbf{General Instructions:}", r"\begin{enumerate}[label=(\arabic*)]"]
    for line in lines:
        out.append(f"\\item {line}")
    out.append(r"\end{enumerate}")
    out.append(r"\vspace{6pt}")
    return "\n".join(out) + "\n"


def _get_text(response) -> str:
    """Normalizes a LangChain model response into plain text.
    Gemini 3.x "thinking" models sometimes return `.content` as a list of
    content blocks (e.g. {"type": "thinking", ...} and {"type": "text", ...})
    instead of a plain string - this pulls out just the text parts."""
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") in (None, "text") and "text" in block:
                    parts.append(block["text"])
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def _finish_reason(response) -> Optional[str]:
    """Pulls the finish_reason out of a LangChain response, when available,
    so a truncated/empty completion can be diagnosed (MAX_TOKENS, SAFETY,
    RECITATION, ...) instead of just showing the raw cut-off text."""
    meta = getattr(response, "response_metadata", None) or {}
    reason = meta.get("finish_reason")
    if reason:
        return str(reason)
    candidates = meta.get("candidates") or []
    if candidates and isinstance(candidates[0], dict):
        return candidates[0].get("finish_reason")
    return None


def _compile_string(latex_source: str, base_name: str, workdir: str):
    os.makedirs(workdir, exist_ok=True)
    tex_path = os.path.join(workdir, base_name + ".tex")
    with open(tex_path, "w") as f:
        f.write(latex_source)
    try:
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", base_name + ".tex"],
            cwd=workdir, capture_output=True, text=True, timeout=60,
        )
        log = result.stdout + result.stderr
        pdf_path = os.path.join(workdir, base_name + ".pdf")
        success = os.path.exists(pdf_path) and result.returncode == 0
        return success, log
    except FileNotFoundError:
        return False, "pdflatex not found on PATH inside the container - check the Dockerfile's texlive install."
    except subprocess.TimeoutExpired as e:
        return False, f"pdflatex timed out: {e}"


def save_outputs(latex_source: str, base_name: str, output_dir: str) -> bool:
    ok, log = _compile_string(latex_source, base_name, output_dir)
    if not ok:
        print("Compile failed:", log[-1000:])
        return False
    pdf_path = os.path.join(output_dir, base_name + ".pdf")
    txt_path = os.path.join(output_dir, base_name + ".txt")
    subprocess.run(["pdftotext", "-layout", pdf_path, txt_path], check=False)
    return True


# ---------------------------------------------------------------------------
# Diagram generation (self-checking TikZ)
# ---------------------------------------------------------------------------
def generate_tikz_diagram(description: str, model, max_attempts: int = 3) -> str:
    if model is None:
        raise RuntimeError("Gemini model not initialised - set GEMINI_API_KEY.")

    prompt = f"""Write ONLY the TikZ drawing commands (contents BETWEEN
\\begin{{tikzpicture}} and \\end{{tikzpicture}} - do not include those two lines)
for this diagram, for a CBSE exam question:

Diagram needed: {description}

Rules:
- Output ONLY valid TikZ drawing commands, no markdown fences, no explanation.
- Label vertices/angles/lengths clearly, standard exam-diagram conventions.
- Keep it clean and appropriately sized for a printed exam paper.
{LATEX_SAFETY_RULES}"""

    tikz_body = _get_text(model.invoke(prompt)).strip()
    tikz_body = tikz_body.replace("```latex", "").replace("```tikz", "").replace("```", "").strip()

    for _ in range(max_attempts):
        test_doc = LATEX_DIAGRAM_TEST_WRAPPER % tikz_body
        ok, log = _compile_string(test_doc, f"diagram_test_{abs(hash(description)) % 100000}", BUILD_DIR)
        if ok:
            return tikz_body
        fix_prompt = f"""This TikZ code failed to compile.

COMPILER ERROR (tail):
{log[-1500:]}

TIKZ CODE:
{tikz_body}

Return ONLY the corrected TikZ body (no wrapper, no fences, no explanation)."""
        tikz_body = _get_text(model.invoke(fix_prompt)).strip()
        tikz_body = tikz_body.replace("```latex", "").replace("```tikz", "").replace("```", "").strip()

    raise RuntimeError(f"Diagram did not compile after {max_attempts} attempts: {description}")


# ---------------------------------------------------------------------------
# Web search grounding
# ---------------------------------------------------------------------------
def search_reference_questions(topic: str, num_results: int = 3) -> List[str]:
    if not TAVILY_API_KEY:
        return []
    from tavily import TavilyClient
    client = TavilyClient(api_key=TAVILY_API_KEY)
    resp = client.search(query=f"CBSE exam sample questions {topic}", max_results=num_results)
    return [r.get("content", "") for r in resp.get("results", [])]


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------
def _extract_json(text: str, finish_reason: Optional[str] = None):
    """Strips markdown fences, then falls back to grabbing the first [...] or
    {...} block if Gemini wrapped the JSON in extra prose despite instructions
    not to."""
    cleaned = re.sub(r"```json|```", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for open_ch, close_ch in [("[", "]"), ("{", "}")]:
        start = cleaned.find(open_ch)
        end = cleaned.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    reason_note = ""
    if finish_reason and finish_reason.upper() not in ("STOP", "1"):
        reason_note = (
            f"\n\nThe model stopped early with finish_reason={finish_reason}, "
            "which usually means the JSON was cut off before it closed "
            "(commonly MAX_TOKENS - try a smaller batch of questions per call, "
            "or SAFETY/RECITATION - try rewording the topics/prompt)."
        )
    raise ValueError(
        f"Could not parse JSON from model output. Raw output was:\n{text[:1000]}{reason_note}"
    )


def _question_schema_for_type(question_type: str) -> str:
    """Returns the JSON-shape instructions for one question, tailored to its
    type. This is what makes MCQs actually carry answer options, assertion-
    reason questions carry a proper assertion/reason pair, and case studies
    carry a passage plus marked subparts - none of which existed before."""
    qtype = question_type.lower()

    if qtype == "mcq":
        return """Each object must have:
- "text": the question stem only (no options embedded, LaTeX-safe)
- "options": an array of EXACTLY 4 plain-text answer options (no "(a)"/"A." prefixes - those are added automatically). Exactly one must be correct; the other three must be plausible, non-absurd distractors.
- "needs_diagram": true/false
- "diagram_description": precise figure description if needs_diagram is true, else null"""

    if qtype == "assertion-reason":
        return """Each object must have:
- "assertion": the Assertion (A) statement text
- "reason": the Reason (R) statement text
- "needs_diagram": false
- "diagram_description": null
Do NOT include the four standard (a)-(d) answer options - those are added automatically and are always the same four fixed statements about whether A and R are true and whether R explains A."""

    if qtype == "case study":
        return """Each object must have:
- "case_text": a short (3-6 sentence) original case/passage/data scenario relevant to the topics (may reference a table/graph described in words if needs_diagram is used for it)
- "subparts": an array of 2-4 objects, each {"text": "...", "marks": <int>}, whose "marks" values sum to EXACTLY the section's marks_each
- "needs_diagram": true/false (true if the case relies on a table, graph, or figure)
- "diagram_description": precise figure/table description if needs_diagram is true, else null
Do not include a top-level "text" field for Case Study questions - use "case_text" and "subparts" instead."""

    # Very Short Answer / Short Answer / Long Answer / anything else
    return """Each object must have:
- "text": the full question text (LaTeX-safe). If the question naturally has labelled parts, leave "text" as a short lead-in (or empty string) and use "subparts" instead.
- "subparts": OPTIONAL array of objects {"text": "...", "marks": <int or null>}. Use this only if the question genuinely divides into (a)/(b)/(c) parts. If each subpart's marks are individually meaningful, set "marks" on every subpart so they sum to marks_each; if the parts instead share one overall mark value, set "marks": null on every subpart.
- "needs_diagram": true/false
- "diagram_description": precise figure description if needs_diagram is true, else null"""


MAX_QUESTIONS_PER_CALL = 8
# Large sections (e.g. an 18-question MCQ Section A) asked for in one shot
# are the most likely thing to get cut off mid-JSON, since Gemini 3.x models
# spend part of the output budget on internal "thinking" before the answer.
# Splitting into smaller batches keeps each call well within budget, and -
# since the batches don't depend on each other - lets them run concurrently
# instead of one-after-another, which is most of where the ~10 minute wall
# time was going.
BATCH_CONCURRENCY = 3
# Free-tier Gemini rate limits are typically ~10-30 requests/minute, so this
# stays modest rather than firing every batch across every section at once.


def _effective_batch_cap(section: Dict[str, Any]) -> int:
    """Internal-choice sections carry a full primary AND alternative question
    per item (roughly double the text of a plain question), and Case Study
    items carry a passage plus several subparts. Both are heavier per-item
    than MAX_QUESTIONS_PER_CALL assumes, so pre-emptively use a smaller cap
    for them instead of relying only on the reactive retry-and-split below."""
    cap = MAX_QUESTIONS_PER_CALL
    if section.get("internal_choice"):
        cap = max(1, cap // 2)
    if (section.get("question_type") or "").lower() == "case study":
        cap = max(1, cap // 2)
    return cap


def generate_section_questions(
    section: Dict[str, Any],
    config: Dict[str, Any],
    model,
    search_context: str = "",
    job_id: Optional[str] = None,
):
    if model is None:
        raise RuntimeError("Gemini model not initialised - set GEMINI_API_KEY.")

    count = section["num_questions"]
    cap = _effective_batch_cap(section)
    if count <= cap:
        questions = _generate_batch_resilient(section, config, model, search_context)
        if job_id:
            _job_log(job_id, f"Generated {section['name']} ({len(questions)} questions)")
        return questions

    batches: List[Dict[str, Any]] = []
    remaining = count
    while remaining > 0:
        batch_size = min(cap, remaining)
        batches.append({**section, "num_questions": batch_size})
        remaining -= batch_size

    results: List[Optional[List[Any]]] = [None] * len(batches)
    with ThreadPoolExecutor(max_workers=min(BATCH_CONCURRENCY, len(batches))) as ex:
        future_to_idx = {
            ex.submit(_generate_batch_resilient, b, config, model, search_context): i
            for i, b in enumerate(batches)
        }
        done_count = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()
            done_count += 1
            if job_id:
                _job_log(job_id, f"{section['name']}: batch {done_count}/{len(batches)} done")

    questions = []
    for batch_result in results:
        questions.extend(batch_result or [])
    return questions


def _generate_batch_resilient(section: Dict[str, Any], config: Dict[str, Any], model, search_context: str = ""):
    """Generates one batch; if the model's JSON comes back truncated (the
    usual cause is one batch being heavier than expected - long internal-
    choice questions, verbose case studies, etc.), automatically retries
    with the batch split in half instead of failing the whole paper.
    Recurses down to single-question calls if needed; only raises once even
    a single question can't be parsed, since there's nothing smaller left
    to try at that point."""
    count = section["num_questions"]
    try:
        return _generate_question_batch(section, config, model, search_context)
    except ValueError:
        if count <= 1:
            raise
        half = count // 2
        first = {**section, "num_questions": half}
        second = {**section, "num_questions": count - half}
        return (
            _generate_batch_resilient(first, config, model, search_context)
            + _generate_batch_resilient(second, config, model, search_context)
        )


def _generate_question_batch(section: Dict[str, Any], config: Dict[str, Any], model, search_context: str = ""):
    schema = _question_schema_for_type(section["question_type"])
    internal_choice = bool(section.get("internal_choice"))
    count = section["num_questions"]

    choice_instructions = ""
    if internal_choice:
        choice_instructions = f"""
IMPORTANT: because this section uses internal choice, every one of the {count}
items in your JSON array must instead be an OBJECT WITH TWO KEYS, "primary" and
"alternative" - each following the schema below independently and completely.
The two alternatives must:
- carry identical marks ({section['marks_each']} each)
- be comparable in difficulty and cognitive demand
- stay within the supplied topics
- not be trivially easier or harder than one another
"""

    master_prompt = build_master_prompt(config)
    master_block = f"{master_prompt}\n\n---\n" if master_prompt else ""

    prompt = f"""{master_block}You are now generating ONLY the "{section['name']}" section of the paper
described above in this call - not the whole paper at once.

Section details for this call:
- Question type: {section['question_type']}
- Number of questions: {count}
- Marks per question: {section['marks_each']}
- Difficulty: {section['difficulty']}
- Topics to draw from: {', '.join(config['topics'])}
{choice_instructions}
Reference context (may be empty):
{search_context[:2000]}

Return a JSON array of exactly {count} objects. {schema}

General rules:
- Every question must be academically accurate and originally written - do not copy real exam questions verbatim.
- No two questions should test the exact same fact in the exact same way.
- Keep language age-appropriate and precise for Class {config['class_name']}.

{LATEX_SAFETY_RULES}

Return ONLY the JSON array, nothing else."""
    response = model.invoke(prompt)
    raw = _get_text(response)
    return _extract_json(raw, finish_reason=_finish_reason(response))


# ---------------------------------------------------------------------------
# Question rendering (JSON -> LaTeX)
# ---------------------------------------------------------------------------
def _render_single_question(q: Dict[str, Any], marks_each: int, model) -> str:
    parts: List[str] = []
    subparts = q.get("subparts") or []
    subparts_have_marks = any(sp.get("marks") for sp in subparts)

    if q.get("assertion") and q.get("reason"):
        parts.append(f"Assertion (A): {q['assertion']}\\\\")
        marks_suffix = "" if subparts_have_marks else f" \\hfill [{marks_each}]"
        parts.append(f"Reason (R): {q['reason']}{marks_suffix}")
        parts.append(r"\begin{enumerate}[label=(\alph*)]")
        for opt in ASSERTION_REASON_OPTIONS:
            parts.append(f"\\item {opt}")
        parts.append(r"\end{enumerate}")
    else:
        stem = (q.get("text") or "").strip()
        case_text = q.get("case_text")
        show_top_marks = not subparts_have_marks
        marks_suffix = f" \\hfill [{marks_each}]" if show_top_marks else ""

        if case_text:
            parts.append(f"\\textit{{{case_text}}}\\\\")
        if stem:
            parts.append(f"{stem}{marks_suffix}")
        elif show_top_marks:
            # No stem to attach marks to (e.g. a pure case-study passage, or
            # subparts that share one overall mark value) - show them on
            # their own line instead of silently dropping them.
            parts.append(f"\\hfill [{marks_each}]")

        options = q.get("options") or []
        if options:
            parts.append(r"\begin{enumerate}[label=(\alph*)]")
            for opt in options:
                parts.append(f"\\item {opt}")
            parts.append(r"\end{enumerate}")

    if subparts:
        parts.append(r"\begin{enumerate}[label=(\alph*)]")
        for sp in subparts:
            sp_marks = f" \\hfill [{sp['marks']}]" if sp.get("marks") else ""
            parts.append(f"\\item {(sp.get('text') or '').strip()}{sp_marks}")
        parts.append(r"\end{enumerate}")

    if q.get("needs_diagram") and q.get("diagram_description"):
        tikz = generate_tikz_diagram(q["diagram_description"], model)
        parts.append(
            f"\\begin{{center}}\n\\begin{{tikzpicture}}\n{tikz}\n\\end{{tikzpicture}}\n\\end{{center}}"
        )

    return "\n".join(parts)


def render_question_block(q: Dict[str, Any], q_num: int, marks_each: int, model) -> str:
    """Renders one fully-numbered question - including options, assertion-
    reason formatting, subparts, diagrams, and an OR-linked internal-choice
    alternative where present - tagged so the editor can target it later."""
    if "primary" in q and "alternative" in q:
        body = (
            _render_single_question(q["primary"], marks_each, model)
            + "\n\\begin{center}\\textbf{OR}\\end{center}\n"
            + _render_single_question(q["alternative"], marks_each, model)
        )
    else:
        body = _render_single_question(q, marks_each, model)

    return (
        f"% %%% Q{q_num}_START\n"
        f"\\item {body}\n"
        f"% %%% Q{q_num}_END"
    )


# ---------------------------------------------------------------------------
# Pipeline (LangGraph)
# ---------------------------------------------------------------------------
from typing import TypedDict
from langgraph.graph import StateGraph, END


class PaperState(TypedDict):
    config: Dict[str, Any]
    sections_data: List[Dict[str, Any]]
    latex_body: str
    compile_ok: bool
    compile_log: str
    retries: int
    job_id: Optional[str]


def node_generate_sections(state: PaperState):
    config = state["config"]
    job_id = state.get("job_id")
    model = get_model(config.get("model_name"))
    sections = config["sections"]

    def _run_section(section):
        ctx_snippets: List[str] = []
        for topic in config["topics"][:2]:
            ctx_snippets.extend(search_reference_questions(topic))
        questions = generate_section_questions(
            section, config, model, "\n".join(ctx_snippets), job_id=job_id
        )
        return {"section": section, "questions": questions}

    # Sections are independent of each other, so - like the question batches
    # inside each one - they run concurrently instead of in a strict loop.
    results: List[Optional[Dict[str, Any]]] = [None] * len(sections)
    with ThreadPoolExecutor(max_workers=min(BATCH_CONCURRENCY, len(sections))) as ex:
        future_to_idx = {ex.submit(_run_section, s): i for i, s in enumerate(sections)}
        for future in as_completed(future_to_idx):
            results[future_to_idx[future]] = future.result()

    return {"sections_data": results}


def node_assemble_latex(state: PaperState):
    config = state["config"]
    job_id = state.get("job_id")
    if job_id:
        _job_log(job_id, "Assembling LaTeX...")
    model = get_model(config.get("model_name"))
    body = build_latex_header(config)
    body += render_general_instructions(config)

    q_num = 1
    first_section = True
    for sd in state["sections_data"]:
        section = sd["section"]
        start_q = q_num
        end_q = q_num + section["num_questions"] - 1
        section_total = section["num_questions"] * section["marks_each"]
        q_range = f"Q.{start_q}" if end_q == start_q else f"Q.{start_q} to Q.{end_q}"

        body += f"\n\\section*{{{section['name']}}}\n"
        body += (
            f"\\textit{{({section['question_type']} --- {section['marks_each']} "
            f"mark(s) each --- {q_range} --- {section_total} marks)}}\n"
        )
        body += r"\begin{enumerate}" + ("[resume]" if not first_section else "") + "\n"
        first_section = False

        for q in sd["questions"]:
            body += render_question_block(q, q_num, section["marks_each"], model) + "\n"
            q_num += 1
        body += "\\end{enumerate}\n"

    body += LATEX_FOOTER
    return {"latex_body": body}


def node_compile(state: PaperState):
    job_id = state.get("job_id")
    if job_id:
        _job_log(job_id, "Compiling PDF...")
    ok, log = _compile_string(state["latex_body"], "generated_paper", BUILD_DIR)
    if job_id:
        _job_log(job_id, "PDF compiled successfully" if ok else "PDF compile failed, attempting a fix...")
    return {"compile_ok": ok, "compile_log": log}


def node_fix_errors(state: PaperState):
    job_id = state.get("job_id")
    if job_id:
        _job_log(job_id, f"Fix attempt {state.get('retries', 0) + 1}...")
    fix_prompt = f"""This full CBSE exam LaTeX document failed to compile.

COMPILER ERROR (tail):
{state['compile_log'][-2000:]}

FULL LATEX SOURCE:
{state['latex_body']}

Return ONLY the corrected, complete LaTeX document (from \\documentclass to \\end{{document}})."""
    model = get_model(state["config"].get("model_name"))
    fixed = _get_text(model.invoke(fix_prompt)).strip()
    fixed = fixed.replace("```latex", "").replace("```", "").strip()
    return {"latex_body": fixed, "retries": state.get("retries", 0) + 1}


def route_after_compile(state: PaperState):
    if state["compile_ok"] or state.get("retries", 0) >= 2:
        return END
    return "fix_errors"


_graph = StateGraph(PaperState)
_graph.add_node("generate_sections", node_generate_sections)
_graph.add_node("assemble_latex", node_assemble_latex)
_graph.add_node("compile", node_compile)
_graph.add_node("fix_errors", node_fix_errors)
_graph.set_entry_point("generate_sections")
_graph.add_edge("generate_sections", "assemble_latex")
_graph.add_edge("assemble_latex", "compile")
_graph.add_conditional_edges("compile", route_after_compile, {"fix_errors": "fix_errors", END: END})
_graph.add_edge("fix_errors", "compile")
paper_graph = _graph.compile()


def edit_question(latex_source: str, question_number: int, edit_instruction: str, model) -> str:
    start_tag = f"% %%% Q{question_number}_START"
    end_tag = f"% %%% Q{question_number}_END"
    start_idx = latex_source.find(start_tag)
    end_idx = latex_source.find(end_tag)
    if start_idx == -1 or end_idx == -1:
        raise ValueError(f"Question {question_number} tags not found in this document.")
    old_block = latex_source[start_idx:end_idx]
    prompt = f"""Here is one question block from a CBSE exam paper, in LaTeX:

{old_block}

Apply this edit instruction: "{edit_instruction}"

Return ONLY the corrected block. Keep the "% %%% Qn_START" comment line at the top,
keep the \\item structure, keep any (a)/(b)/(c) option or subpart lists in their
existing \\begin{{enumerate}}[label=(\\alph*)] form unless the instruction asks you
to change them, and if you add/change a diagram, keep it inside
\\begin{{center}}\\begin{{tikzpicture}}...\\end{{tikzpicture}}\\end{{center}}."""
    new_block = _get_text(model.invoke(prompt)).strip().replace("```latex", "").replace("```", "").strip()
    return latex_source[:start_idx] + new_block + "\n" + latex_source[end_idx:]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Prashna.ai - CBSE Question Paper Generator")
api = APIRouter(prefix="/api")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    # Print the full traceback to container logs (still visible via `docker logs`),
    # but also return the error type + message directly in the API response so
    # you don't need to go dig through logs for every failure.
    tb = traceback.format_exc()
    print(tb, flush=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "hint": "Full traceback is in `docker logs prashna-ai-container --tail 100` if this message isn't enough.",
        },
    )


class SectionConfig(BaseModel):
    name: str
    question_type: str
    num_questions: int
    marks_each: int
    difficulty: str
    internal_choice: bool = False


class PaperConfig(BaseModel):
    board: str = "CBSE"
    class_name: str = "10"
    subject: str = "Mathematics"
    duration_minutes: int = 180
    max_marks: int = 80
    model_name: str = "gemini-3.1-flash-lite"
    topics: List[str] = DEFAULT_CONFIG["topics"]
    sections: List[SectionConfig] = [SectionConfig(**s) for s in DEFAULT_CONFIG["sections"]]


class EditRequest(BaseModel):
    question_number: int
    instruction: str


@api.get("/health")
def health():
    return {
        "status": "ok",
        "gemini_configured": bool(GEMINI_API_KEY),
        "tavily_configured": bool(TAVILY_API_KEY),
        "pdflatex_found": shutil.which("pdflatex") is not None,
        "prompt_template_loaded": bool(_load_prompt_template()),
    }


@api.get("/papers")
def list_papers():
    """Backs the frontend's history panel, which uses this to detect
    entries that reference a paper_id no longer held in memory (e.g.
    after a server restart, since PAPERS is in-memory only)."""
    return {
        "papers": [
            {"paper_id": pid, "compiled": data.get("compiled", False)}
            for pid, data in PAPERS.items()
        ]
    }


@api.get("/subjects")
def list_subjects():
    """Powers the Subject dropdown's curated-preset list."""
    return {"subjects": list(SUBJECT_LIBRARY.keys())}


@api.get("/subjects/{subject}/template")
def get_subject_template(subject: str):
    """Returns curated topics + a full section blueprint for a subject, so
    picking a subject in the UI can one-click populate the rest of the form
    instead of a teacher hand-typing every topic and section row."""
    lib = SUBJECT_LIBRARY.get(subject)
    if not lib:
        raise HTTPException(status_code=404, detail=f"No curated template for subject '{subject}'.")
    return {"subject": subject, "topics": lib["topics"], "sections": lib["sections"]}


@api.post("/papers/self-test")
def self_test():
    """Generates a hardcoded sample paper with a TikZ diagram - no API calls.
    Use this right after `docker run` to confirm the container's LaTeX setup works."""
    sample_latex = build_latex_header(DEFAULT_CONFIG) + r"""
\section*{Section A (Sample)}
\begin{enumerate}
% %%% Q1_START
\item In the given figure, $\triangle ABC$ is right-angled at $B$. Find the length of $AC$. \hfill [3]
\begin{center}
\begin{tikzpicture}[scale=1.1]
  \draw[thick] (0,0) -- (4,0) -- (4,3) -- cycle;
  \draw (3.7,0) -- (3.7,0.3) -- (4,0.3);
  \node[below] at (0,0) {$A$};
  \node[below] at (4,0) {$B$};
  \node[above] at (4,3) {$C$};
  \node[below] at (2,0) {$4$ cm};
  \node[right] at (4,1.5) {$3$ cm};
\end{tikzpicture}
\end{center}
% %%% Q1_END
% %%% Q2_START
\item Solve for $x$: $2x^2 - 5x + 3 = 0$. \hfill [2]
\begin{enumerate}[label=(\alph*)]
\item $x = 1, \ x = 1.5$
\item $x = -1, \ x = -1.5$
\item $x = 1, \ x = -1.5$
\item $x = -1, \ x = 1.5$
\end{enumerate}
% %%% Q2_END
\end{enumerate}
""" + LATEX_FOOTER

    paper_id = "self-test"
    ok = save_outputs(sample_latex, paper_id, OUTPUT_DIR)
    PAPERS[paper_id] = {"latex": sample_latex, "compiled": ok, "model_name": DEFAULT_CONFIG["model_name"]}
    if not ok:
        raise HTTPException(status_code=500, detail="LaTeX compilation failed - check container logs.")
    return {"paper_id": paper_id, "compiled": True}


@api.post("/generate-paper")
def generate_paper(config: PaperConfig = None):
    """Synchronous generation - blocks until the paper is done. Kept for
    backwards compatibility / scripts; the UI should use
    /generate-paper/start + /jobs/{job_id}/stream instead, since that path
    now runs sections concurrently and reports live progress instead of
    leaving the customer staring at a blank spinner for several minutes."""
    if get_model() is None:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not set on the server.")
    cfg = config.dict() if config else DEFAULT_CONFIG

    final_state = paper_graph.invoke({
        "config": cfg, "sections_data": [], "latex_body": "",
        "compile_ok": False, "compile_log": "", "retries": 0, "job_id": None,
    })

    paper_id = str(uuid.uuid4())[:8]
    if not final_state["compile_ok"]:
        raise HTTPException(status_code=500, detail=final_state["compile_log"][-1500:])

    save_outputs(final_state["latex_body"], paper_id, OUTPUT_DIR)
    PAPERS[paper_id] = {
        "latex": final_state["latex_body"],
        "compiled": True,
        "model_name": cfg.get("model_name", DEFAULT_CONFIG["model_name"]),
    }
    return {"paper_id": paper_id, "compiled": True}


def _run_generation_job(job_id: str, cfg: Dict[str, Any]):
    """Runs the full generate -> assemble -> compile (-> fix -> recompile)
    pipeline in a background thread, writing progress into JOBS[job_id] as
    it goes so /jobs/{job_id}/stream has something to report."""
    try:
        final_state = paper_graph.invoke({
            "config": cfg, "sections_data": [], "latex_body": "",
            "compile_ok": False, "compile_log": "", "retries": 0, "job_id": job_id,
        })

        if not final_state["compile_ok"]:
            _job_set(job_id, status="error", error=final_state["compile_log"][-1500:])
            return

        paper_id = str(uuid.uuid4())[:8]
        _job_log(job_id, "Saving output files...")
        save_outputs(final_state["latex_body"], paper_id, OUTPUT_DIR)
        PAPERS[paper_id] = {
            "latex": final_state["latex_body"],
            "compiled": True,
            "model_name": cfg.get("model_name", DEFAULT_CONFIG["model_name"]),
        }
        _job_log(job_id, "Done.")
        _job_set(job_id, status="done", paper_id=paper_id)
    except Exception as exc:  # noqa: BLE001 - report to the job, don't crash the thread silently
        _job_set(job_id, status="error", error=f"{type(exc).__name__}: {exc}")


@api.post("/generate-paper/start")
def generate_paper_start(config: PaperConfig = None):
    """Kicks off generation in the background and returns immediately with
    a job_id. Poll progress via GET /generate-paper/jobs/{job_id}/stream
    (Server-Sent Events) instead of waiting on this call."""
    if get_model() is None:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not set on the server.")
    cfg = config.dict() if config else DEFAULT_CONFIG

    job_id = str(uuid.uuid4())[:8]
    _job_create(job_id)
    threading.Thread(target=_run_generation_job, args=(job_id, cfg), daemon=True).start()
    return {"job_id": job_id}


@api.get("/generate-paper/jobs/{job_id}/stream")
def stream_generation_job(job_id: str):
    """Server-Sent Events stream of progress for a job started via
    /generate-paper/start. Each event is a JSON object with the job's
    current status and log lines; the stream closes once status is "done"
    or "error". Frontend usage: `new EventSource(...)` and re-render on
    each `message` event."""
    if _job_snapshot(job_id) is None:
        raise HTTPException(status_code=404, detail="Unknown job_id.")

    def event_stream():
        sent = 0
        while True:
            job = _job_snapshot(job_id)
            if job is None:
                break
            new_lines = job["log"][sent:]
            sent = len(job["log"])
            payload = {
                "status": job["status"],
                "new_log": new_lines,
                "paper_id": job.get("paper_id"),
                "error": job.get("error"),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.6)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@api.post("/papers/{paper_id}/edit-question")
def edit_paper_question(paper_id: str, req: EditRequest):
    if paper_id not in PAPERS:
        raise HTTPException(status_code=404, detail="Unknown paper_id.")
    paper = PAPERS[paper_id]
    model = get_model(paper.get("model_name"))
    if model is None:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not set on the server.")

    latex_source = paper["latex"]
    try:
        new_latex = edit_question(latex_source, req.question_number, req.instruction, model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ok = save_outputs(new_latex, paper_id, OUTPUT_DIR)
    if not ok:
        raise HTTPException(status_code=500, detail="Recompilation failed after the edit.")
    PAPERS[paper_id] = {**paper, "latex": new_latex, "compiled": True}
    return {"paper_id": paper_id, "compiled": True}


@api.get("/papers/{paper_id}/download")
def download_paper(paper_id: str, format: str = "pdf"):
    if format not in ("pdf", "tex", "txt"):
        raise HTTPException(status_code=400, detail="format must be pdf, tex, or txt")
    path = os.path.join(OUTPUT_DIR, f"{paper_id}.{format}")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"No {format} file found for paper_id={paper_id}")
    # PDFs need to render inside the preview <iframe>, which only works with
    # Content-Disposition: inline. FileResponse defaults to "attachment"
    # whenever a filename is given, which makes browsers try (and silently
    # fail) to download the file inside the iframe instead of showing it -
    # hence a blank preview pane even though the request succeeds.
    # .tex/.txt keep "attachment" so the explicit download links still
    # trigger Save-As instead of opening in a new tab.
    disposition = "inline" if format == "pdf" else "attachment"
    return FileResponse(
        path,
        filename=f"{paper_id}.{format}",
        content_disposition_type=disposition,
    )


app.include_router(api)


@app.get("/healthz")
def healthz():
    """Plain infra-level health check (container orchestrators, `docker healthcheck`, etc.)
    kept separate from /api/health, which the frontend polls for the status pills."""
    return {"status": "ok"}


@app.get("/")
def serve_frontend():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend not found - static/index.html is missing.")
    return FileResponse(index_path)


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    missing_assets = [
        f for f in ("favicon-32.png", "favicon-16.png", "favicon-180.png", "favicon.ico")
        if not os.path.exists(os.path.join(STATIC_DIR, "assets", f))
    ]
    if missing_assets:
        print(f"WARNING: static/assets is missing: {', '.join(missing_assets)}", flush=True)
else:
    print(f"WARNING: STATIC_DIR ({STATIC_DIR}) does not exist - /static/* will 404, "
          f"including the favicon and logo.", flush=True)