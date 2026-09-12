import os
import re
import json
import shutil
import subprocess
import traceback
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
BUILD_DIR = os.environ.get("BUILD_DIR", "/app/build")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(BUILD_DIR, exist_ok=True)

DEFAULT_CONFIG: Dict[str, Any] = {
    "board": "CBSE",
    "class_name": "10",
    "subject": "Mathematics",
    "duration_minutes": 180,
    "max_marks": 80,
    "model_name": "gemini-3.1-flash-lite",
    "topics": [
        "Real Numbers", "Polynomials", "Quadratic Equations", "Triangles",
        "Coordinate Geometry", "Trigonometry", "Circles", "Statistics", "Probability",
    ],
    "sections": [
        {"name": "Section A", "question_type": "MCQ",          "num_questions": 4, "marks_each": 1, "difficulty": "easy"},
        {"name": "Section B", "question_type": "Short Answer", "num_questions": 3, "marks_each": 2, "difficulty": "medium"},
        {"name": "Section C", "question_type": "Short Answer", "num_questions": 2, "marks_each": 3, "difficulty": "medium"},
        {"name": "Section D", "question_type": "Long Answer",  "num_questions": 2, "marks_each": 5, "difficulty": "hard"},
        {"name": "Section E", "question_type": "Case Study",   "num_questions": 1, "marks_each": 4, "difficulty": "mixed"},
    ],
}

# In-memory paper registry: {paper_id: {"latex": str, "compiled": bool}}
# A real deployment should replace this with Postgres + S3/Supabase Storage,
# same as the career-agent-saas / ClaimPilot pattern.
PAPERS: Dict[str, Dict[str, Any]] = {}

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
\textit{General Instructions: This question paper follows the """ + config["board"] + r""" format guidelines.}
\vspace{6pt}
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
- Keep it clean and appropriately sized for a printed exam paper."""

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
def _extract_json(text: str):
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

    raise ValueError(f"Could not parse JSON from model output. Raw output was:\n{text[:1000]}")


def generate_section_questions(section: Dict[str, Any], config: Dict[str, Any], model, search_context: str = ""):
    if model is None:
        raise RuntimeError("Gemini model not initialised - set GEMINI_API_KEY.")
    prompt = f"""You are setting the "{section['name']}" section of a {config['board']} Class
{config['class_name']} {config['subject']} exam paper.

Section details:
- Question type: {section['question_type']}
- Number of questions: {section['num_questions']}
- Marks per question: {section['marks_each']}
- Difficulty: {section['difficulty']}
- Topics to draw from: {', '.join(config['topics'])}

Reference context (may be empty):
{search_context[:2000]}

Return a JSON array of exactly {section['num_questions']} objects, each with keys:
- "text": the full question text (plain LaTeX-safe text, no diagram description inside it)
- "needs_diagram": true/false
- "diagram_description": if needs_diagram is true, a precise description of the figure needed; otherwise null

Return ONLY the JSON array, nothing else."""
    raw = _get_text(model.invoke(prompt))
    return _extract_json(raw)


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


def node_generate_sections(state: PaperState):
    config = state["config"]
    model = get_model(config.get("model_name"))
    sections_data = []
    for section in config["sections"]:
        ctx_snippets: List[str] = []
        for topic in config["topics"][:2]:
            ctx_snippets.extend(search_reference_questions(topic))
        questions = generate_section_questions(section, config, model, "\n".join(ctx_snippets))
        sections_data.append({"section": section, "questions": questions})
    return {"sections_data": sections_data}


def node_assemble_latex(state: PaperState):
    config = state["config"]
    model = get_model(config.get("model_name"))
    body = build_latex_header(config)
    q_num = 1
    for sd in state["sections_data"]:
        section = sd["section"]
        body += f"\n\\section*{{{section['name']}}}\n"
        body += f"\\textit{{({section['question_type']}, {section['marks_each']} marks each)}}\n"
        body += "\\begin{enumerate}\n"
        for q in sd["questions"]:
            body += f"% %%% Q{q_num}_START\n"
            body += f"\\item {q['text']}\n"
            if q.get("needs_diagram"):
                tikz = generate_tikz_diagram(q["diagram_description"], model)
                body += f"\\begin{{center}}\n\\begin{{tikzpicture}}\n{tikz}\n\\end{{tikzpicture}}\n\\end{{center}}\n"
            body += f"% %%% Q{q_num}_END\n"
            q_num += 1
        body += "\\end{enumerate}\n"
    body += LATEX_FOOTER
    return {"latex_body": body}


def node_compile(state: PaperState):
    ok, log = _compile_string(state["latex_body"], "generated_paper", BUILD_DIR)
    return {"compile_ok": ok, "compile_log": log}


def node_fix_errors(state: PaperState):
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
keep the \\item structure, and if you add/change a diagram, keep it inside
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


@api.post("/papers/self-test")
def self_test():
    """Generates a hardcoded sample paper with a TikZ diagram - no API calls.
    Use this right after `docker run` to confirm the container's LaTeX setup works."""
    sample_latex = build_latex_header(DEFAULT_CONFIG) + r"""
\section*{Section A (Sample)}
\begin{enumerate}
% %%% Q1_START
\item In the given figure, $\triangle ABC$ is right-angled at $B$. Find the length of $AC$.
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
\item Solve for $x$: $2x^2 - 5x + 3 = 0$.
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
    if get_model() is None:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not set on the server.")
    cfg = config.dict() if config else DEFAULT_CONFIG

    final_state = paper_graph.invoke({
        "config": cfg, "sections_data": [], "latex_body": "",
        "compile_ok": False, "compile_log": "", "retries": 0,
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
    return FileResponse(path, filename=f"{paper_id}.{format}")


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