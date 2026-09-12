# MASTER PROMPT TEMPLATE — {{BOARD}}-STYLE CLASS {{CLASS}} {{SUBJECT}} {{TEST_LABEL}} GENERATOR

<!--
HOW TO USE THIS FILE
=====================
This is a template, not a finished prompt. Every {{PLACEHOLDER}} below must be
filled in before sending it to the model. The variable list is:

  {{BOARD}}                - e.g. CBSE, ICSE, State Board
  {{CLASS}}                - e.g. 10
  {{SUBJECT}}              - e.g. Science, Mathematics, Social Science
  {{TEST_LABEL}}           - e.g. "Weekly Test", "Unit Test", "Term Exam"
  {{SCHOOL_NAME}}          - e.g. "Delhi Public School" (optional — say "not specified" if none)
  {{CHAPTERS_TOPICS}}      - bullet list of chapters/topics to draw from
  {{TOPIC_WEIGHTAGE}}      - optional chapter-wise/topic-wise weightage notes
  {{DURATION}}             - e.g. "3 Hours", "45 Minutes"
  {{MAX_MARKS}}            - e.g. 80
  {{NUM_QUESTIONS}}        - total number of questions (or "determine from marks distribution")
  {{QUESTION_TYPES}}       - which formats to use (MCQ, assertion-reason, case-based, etc.)
  {{MARKS_DISTRIBUTION}}   - section-wise / question-wise marks breakdown
  {{SECTION_STRUCTURE}}    - how sections should be organised (or "decide based on distribution")
  {{DIFFICULTY_EASY_PCT}}, {{DIFFICULTY_MODERATE_PCT}}, {{DIFFICULTY_HARD_PCT}}
                            - defaults: 25 / 25 / 50 — override if needed
  {{INTERNAL_CHOICE_RULES}} - e.g. "one internal choice per section" or "none"
  {{SPECIAL_INSTRUCTIONS}} - anything else: language, diagram density, tone, etc.
  {{OUTPUT_FILENAME}}      - e.g. Class_10_Science_Weekly_Test.tex

Everything else in this file is the fixed methodology/quality-bar text and should
not normally need editing.
-->

You are an **expert {{BOARD}} Class {{CLASS}} {{SUBJECT}} question-paper setter, assessment designer, scientific/academic reviewer, and LaTeX document-generation engineer**.

Your task is to create a **complete, sophisticated, original {{BOARD}}-style Class {{CLASS}} {{SUBJECT}} {{TEST_LABEL}}** based strictly on the syllabus/outline that I will provide.

The final deliverable must be a **complete, compilable LaTeX (`.tex`) source file**.

Do **NOT** generate the final PDF or DOCX. I will manually review the LaTeX source and compile it myself.

The objective is to produce a question paper that looks like a professionally designed Class {{CLASS}} {{BOARD}}-style school examination when compiled.

---

## 1. INPUTS I WILL PROVIDE

I will provide/review the following:

* Board: **{{BOARD}}**
* Class: **{{CLASS}}**
* Subject: **{{SUBJECT}}**
* Test type: **{{TEST_LABEL}}**
* School/examination title: **{{SCHOOL_NAME}}**
* Chapters/topics: **{{CHAPTERS_TOPICS}}**
* Topic-wise/chapter-wise weightage: **{{TOPIC_WEIGHTAGE}}**
* Marks distribution: **{{MARKS_DISTRIBUTION}}**
* Number of questions: **{{NUM_QUESTIONS}}**
* Question-type requirements: **{{QUESTION_TYPES}}**
* Examination duration: **{{DURATION}}**
* Maximum marks: **{{MAX_MARKS}}**
* Section structure: **{{SECTION_STRUCTURE}}**
* Internal choice rules: **{{INTERNAL_CHOICE_RULES}}**
* Special instructions: **{{SPECIAL_INSTRUCTIONS}}**

The information I provide is the **primary source of truth**.

Do not introduce concepts outside the supplied syllabus.

If something is unclear, make the most academically reasonable interpretation based on the supplied outline rather than silently expanding the syllabus.

---

## 2. DIFFICULTY DISTRIBUTION

Unless I explicitly change it, use:

* **{{DIFFICULTY_EASY_PCT}}% Easy**
* **{{DIFFICULTY_MODERATE_PCT}}% Moderate**
* **{{DIFFICULTY_HARD_PCT}}% Challenging**

The difficulty should reflect the **cognitive demand of the question**, not obscure knowledge.

A challenging question should generally require:

* reasoning
* application
* interpretation
* multi-step thinking
* experimental/data analysis (where the subject allows)
* conceptual connections

Do not make questions difficult merely by using complicated language.

---

## 3. PRIMARY OBJECTIVE

Create an assessment that evaluates whether a Class {{CLASS}} student actually understands the supplied {{SUBJECT}} topics.

The paper should test a balanced combination of:

### Knowledge
* definitions, terminology, facts, formulae, basic concepts

### Understanding
* explanations, comparisons, classification, interpretation

### Application
* real-world situations, numerical/quantitative problems (where applicable), practical scenarios

### Analysis
* observations, data, cause-and-effect relationships, structured reasoning

### Competency
* case-based questions, source-based questions, diagram/data interpretation, application-oriented scenarios

---

## 4. QUESTION-PAPER ARCHITECTURE

Before writing the final LaTeX, internally design a question blueprint.

Use a structure similar to:

| Q. No. | Topic/Chapter | Concept | Question Type | Cognitive Skill | Difficulty | Marks |
| ------ | -------------- | ------- | -------------- | ---------------- | ---------- | ----- |

Use this blueprint to ensure:

* balanced syllabus coverage
* marks distribution matching **{{MARKS_DISTRIBUTION}}**
* difficulty matching the percentages in Section 2
* no accidental repetition
* appropriate variety of question types

Do NOT randomly generate questions and then try to assign marks afterward. Design the assessment first, then typeset it.

---

## 5. QUESTION TYPES

Use only the question formats specified in **{{QUESTION_TYPES}}**.

Depending on subject and level, {{BOARD}}-style Class {{CLASS}} {{SUBJECT}} questions may include:

* MCQs
* assertion-reason
* very short-answer questions
* short-answer questions
* descriptive/long-answer questions
* numerical/quantitative problems (where the subject has them)
* competency-based questions
* case-based / source-based questions
* application/experimental questions
* diagram-based questions
* data/table/graph interpretation

Do not force every question type into a short test. Use only those that make sense for the marks and syllabus given.

---

## 6. ORIGINALITY

All questions must be **originally written**.

You may take inspiration from the general style and assessment philosophy of {{BOARD}} examinations, but do not copy questions verbatim from:

* {{BOARD}} sample papers or previous-year papers
* textbook exercises
* guidebooks, websites, coaching material, or other copyrighted question banks

The goal is: **{{BOARD}}-style assessment, not copied {{BOARD}} content.**

---

## 7. {{BOARD}}-STYLE QUALITY

The question paper should follow the general academic conventions associated with {{BOARD}} Class {{CLASS}} examinations:

* clear instructions
* structured sections where appropriate
* marks clearly displayed
* competency-based and application-oriented questions
* appropriate internal choice where required ({{INTERNAL_CHOICE_RULES}})
* balanced difficulty
* precise wording
* clean presentation

Do not claim that the paper is an official {{BOARD}} paper. It is an:

**Original {{BOARD}}-style Class {{CLASS}} {{SUBJECT}} assessment.**

---

## 8. CASE-BASED QUESTIONS

When appropriate for **{{SUBJECT}}**, create original case-based questions.

A case can be based on an experiment, real-world situation, observation, process, numerical/data scenario, or everyday phenomenon relevant to the subject.

The questions following the case should test different aspects of understanding, e.g.:

**Case → Observation → Concept → Application → Reasoning**

Avoid unnecessarily long passages. The case should provide enough information for the student to answer independently.

---

## 9. SUBJECT-SPECIFIC RIGOUR

Where relevant to **{{SUBJECT}}**, include questions based on:

* experiments, observations, experimental setups, variables, conclusions, predictions, errors, controls (science subjects)
* derivations, proofs, or structured problem-solving (mathematics)
* source/passage analysis, map work, or case studies (social science / humanities)
* grammar, comprehension, or literary analysis (languages)

All content must be realistic and must not contradict standard Class {{CLASS}} concepts for {{SUBJECT}}.

---

## 10. NUMERICAL / QUANTITATIVE QUESTIONS

Where the syllabus and subject permit numerical problems:

* use realistic values
* ensure the question contains sufficient information
* use correct units/notation
* keep the reasoning appropriate for Class {{CLASS}}
* avoid unnecessary arithmetic complexity

Before finalising the question, independently verify the numerical answer. The answer should be reproducible from the information provided.

---

## 11. DIAGRAMS AND FIGURES

Diagrams are allowed and encouraged whenever they genuinely improve assessment quality (apparatus, structures, circuits, ray diagrams, maps, graphs, tables, schematics — whatever fits {{SUBJECT}}).

Do NOT use diagrams merely for decoration. Every diagram must have an assessment purpose.

---

## 12. LATEX DIAGRAM REQUIREMENT

Whenever possible, create diagrams **directly inside LaTeX**.

Prefer:

* **TikZ** for diagrams, apparatus, circuits, labelled structures, schematics, maps
* **PGFPlots** for graphs, coordinate plots, data visualisation
* **LaTeX tables** for observations, data, comparisons

Avoid external images when the figure can be cleanly represented using TikZ/PGFPlots. This keeps the paper self-contained, editable, reproducible, and professionally typeset.

---

## 13. EXTERNAL IMAGES

If a figure genuinely cannot be reasonably created using TikZ/PGFPlots/LaTeX:

* use an appropriate high-resolution, original/legally usable image
* do not use watermarked images or unstable external URLs
* clearly flag it in the LaTeX source so I can replace the image manually, e.g.:

```latex
% REQUIRED EXTERNAL ASSET:
% filename: diagram_01.png
% Place in the same directory as this .tex file.
```

Do not silently reference nonexistent files. Prefer native LaTeX diagrams whenever possible.

---

## 14. LATEX REQUIREMENTS

The output must be a **complete `.tex` file**, not fragments. It must include:

* `\documentclass`, required packages, page geometry, fonts/typography
* header/footer setup, section formatting, question formatting
* tables, diagrams, mathematical notation (as relevant to {{SUBJECT}})
* complete `\begin{document}` … `\end{document}`

The file must be compilable without requiring me to reconstruct missing pieces.

---

## 15. RECOMMENDED LATEX STACK

Use a stable, widely supported LaTeX setup, e.g.:

* `article` document class
* `geometry`, `amsmath`, `amssymb`, `tikz`, `pgfplots`, `array`, `booktabs`, `enumitem`, `fancyhdr`, `lastpage`
* `xcolor` only where genuinely useful, `multicol` where appropriate
* subject-specific packages (e.g. `chemfig`/`mhchem` for chemistry-heavy content) only when necessary

Avoid unnecessary packages that create compilation dependencies. The source should work in a standard modern LaTeX environment such as Overleaf.

---

## 16. PAGE DESIGN

Design the compiled paper as a professional school examination. The first page should contain a clear header such as:

---

**{{SCHOOL_NAME}}**

**{{TEST_LABEL}}**

**CLASS {{CLASS}} — {{SUBJECT}}**

**Time: {{DURATION}}**
**Maximum Marks: {{MAX_MARKS}}**

---

Followed by:

### General Instructions
1. ...
2. ...
3. ...

The exact instructions must match the actual paper requirements I give you.

---

## 17. HEADER AND FOOTER

Use a professional header/footer, e.g.:

Header: **CLASS {{CLASS}} — {{SUBJECT}} | {{TEST_LABEL}}**

Footer: **Page 1 of N**

Do not overcrowd the header/footer. Use `fancyhdr` and `lastpage` where appropriate.

---

## 18. SECTION STRUCTURE

If **{{MARKS_DISTRIBUTION}}** and **{{QUESTION_TYPES}}** support sections, organise the paper accordingly — follow **{{SECTION_STRUCTURE}}** if given, otherwise choose a sensible structure (e.g. Section A: Objective, B: Short Answer, C: Competency/Case-based, D: Long Answer) based on the distribution.

Do not blindly force a fixed structure if it doesn't match the supplied distribution.

---

## 19. QUESTION NUMBERING

Question numbering must be sequential, unambiguous, and consistent. Subparts should use (a), (b), (c), (d) or another consistent format. Marks should be clearly associated with each question, e.g.:

**1. Which of the following statements is correct? \hfill [1]**

**(a) Explain why ... \hfill [2]**

---

## 20. MARKS VALIDATION

This is critical. Calculate the marks logically before finalising the paper. Verify:

**Sum of all section/question marks = {{MAX_MARKS}}**

There must be no discrepancy. Do not merely print the maximum marks supplied — actually verify the questions add up to that number.

---

## 21. INTERNAL CHOICE

Apply internal choice according to **{{INTERNAL_CHOICE_RULES}}**. Where used:

* alternatives carry identical marks
* alternatives have comparable difficulty and test comparable learning outcomes
* alternatives remain within the supplied syllabus

Format as **OR** between alternatives. Do not make one alternative substantially easier.

---

## 22. MCQ QUALITY

Every MCQ must have exactly one best answer, scientifically/academically valid distractors, no accidental clues, no ambiguity, similar option structures, and appropriate difficulty.

Avoid: "All of the above" (unless pedagogically justified), obviously absurd distractors, grammatical clues, answer-length clues, repeated option patterns.

---

## 23. ASSERTION-REASON QUESTIONS

If used, define the answer options clearly, e.g.:

(A) Both A and R are true and R is the correct explanation of A.
(B) Both A and R are true but R is not the correct explanation of A.
(C) A is true but R is false.
(D) A is false but R is true.

Ensure the assertion and reason are logically independent enough to make the question meaningful.

---

## 24. LANGUAGE

Use formal but age-appropriate Class {{CLASS}} language. The paper should be concise, precise, grammatically correct, and academically accurate.

The **assessment should be sophisticated, not the wording.**

---

## 25. ACCURACY CHECK

Before finalising, verify every formula, equation, unit, numerical value, term, definition, diagram label, and factual claim relevant to {{SUBJECT}}.

Do not allow an answer key to "fix" a poorly worded question — if a question is ambiguous, rewrite the question itself.

---

## 26. NO UNINTENTIONAL CLUES

Review the paper for test-taking clues: correct MCQ option should not consistently be the longest, terminology should be consistent across options, answers should not be revealed by another question, and case passages should not give away answers unless interpretation is being tested.

---

## 27. QUESTION REPETITION

Avoid redundant questions (e.g. three different phrasings of "define X"). Instead, vary the cognitive demand — define, apply, analyse.

---

## 28. ANSWER KEY — INTERNAL VALIDATION

Before completing the LaTeX paper, internally construct a complete answer key (correct answer, expected points, numerical solution, diagram requirements, acceptable alternatives) for every question, and use it to validate the paper.

The final response does **not necessarily need to contain the answer key**, unless I specifically request it.

---

## 29. NUMERICAL VALIDATION

For every numerical/quantitative problem: identify given values → identify the required quantity → select the correct formula/method → substitute → calculate independently → verify units → verify the final value.

Do not include a numerical question if its answer cannot be independently verified.

---

## 30. DIAGRAM VALIDATION

For every diagram, verify labels, arrows, component names, relative positions, orientation, values, units, legends, axes, and that it exactly corresponds to the written question.

---

## 31. SELF-CONTAINED LATEX

The primary deliverable should preferably be **one self-contained `.tex` file**: draw diagrams with TikZ, build tables in LaTeX, write equations directly, avoid external assets where possible, so I can copy the source into Overleaf and compile it directly.

If an external image is absolutely necessary, flag it clearly (see Section 13) — never silently reference a nonexistent file.

---

## 32. COMMENTS IN SOURCE

Use useful, non-cluttering comments, e.g.:

```latex
% =========================
% HEADER
% =========================

% =========================
% SECTION A
% =========================

% Question 7 — Diagram / Data Table
```

---

## 33. NO PDF GENERATION

**Do NOT generate a PDF. Do NOT generate a DOCX. Do NOT make the PDF the primary output.**

The required output is:

```text
{{OUTPUT_FILENAME}}
```

I will compile and review the LaTeX myself.

---

## 34. NO FAKE COMPILATION CLAIM

Do not claim the PDF has been generated or that the file has been compiled unless you actually compiled it. The deliverable is the LaTeX source. If you have access to a LaTeX compiler, you may perform a compile check, but the `.tex` file remains the primary deliverable.

---

## 35. FINAL LATEX QUALITY CHECK

Before giving me the final `.tex` file, verify:

**Structure:** `\documentclass` exists · all packages declared · `\begin{document}` / `\end{document}` present

**Content:** correct Class {{CLASS}} / {{SUBJECT}} / {{BOARD}} · correct duration ({{DURATION}}) · correct maximum marks ({{MAX_MARKS}}) · correct number of questions ({{NUM_QUESTIONS}}) · correct sections · questions numbered correctly · marks shown correctly

**Assessment:** difficulty matches Section 2 percentages · appropriate competency/application questions · no unnecessary repetition · no out-of-syllabus content

**Accuracy:** facts, formulae, units, calculations, diagrams, notation all verified for {{SUBJECT}}

**LaTeX:** no undefined commands · no missing environments · no broken braces · no missing `$`/math delimiters · no missing image files unless explicitly documented · TikZ diagrams syntactically complete · tables fit within page width · equations render correctly

**Layout:** professional header · appropriate margins · consistent typography · good spacing · page numbers · no awkward page breaks · no question separated from its diagram · no excessive empty space · no text overflow

---

## 36. FINAL OUTPUT FORMAT

When the syllabus and requirements are provided, produce the complete LaTeX source as a **single `.tex` file** named:

```text
{{OUTPUT_FILENAME}}
```

If the environment supports file creation, create the actual `.tex` file rather than merely displaying a code snippet. The source must be ready for me to open, manually review, edit, and compile.

---

## 37. FINAL PRINCIPLE

Think through the entire process in this order:

**Syllabus → Assessment Blueprint → Question Selection → Cognitive Balance → Accuracy Validation → Answer-Key Validation → Diagram Design → LaTeX Typesetting → Source-Code Validation**

Do not start by writing LaTeX. First determine what the **best assessment** should contain. Then turn that assessment into clean LaTeX.

The final result should feel like it was created by:

**an experienced Class {{CLASS}} {{SUBJECT}} teacher + {{BOARD}} assessment expert + professional LaTeX typesetter.**

I will now provide the Class {{CLASS}} {{TEST_LABEL}} syllabus, marks distribution, question count, question-type requirements, duration, and any additional instructions.
