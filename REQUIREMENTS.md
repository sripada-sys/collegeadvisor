# MathMentor — Product Requirements
**Version**: 1.0  
**Date**: 2026-04-19  
**Status**: Live

---

## Overview

A local-network AI tutoring system for a Class 12 student preparing for JEE/Board exams.  
Runs on a Linux NUC (server + dashboard). Student uses phone camera to upload work. Parent monitors from any browser on the same WiFi. No internet install needed.

---

## Architecture

| Component | Role |
|---|---|
| Linux NUC `192.168.0.31:5000` | Flask server, SQLite DB, systemd service (`mathtutor`) |
| PC browser `/` | Parent/student dashboard |
| Phone browser `/phone` | Camera upload interface |
| GitHub `sripada-sys/collegeadvisor` | Code distribution + daily DB backup |

**Stack**: Python 3 · Flask · flask-sock · SQLite · Gemini / OpenAI / Claude / Perplexity APIs

---

## AI Model Router

- **Priority order**: Claude → GPT-4o → Gemini Flash → Perplexity Sonar
- Task-level routing: `evaluate`, `explain`, `practice` assigned independently
- Health check on startup — marks each model `ok` / `no_credits` / `error`
- Auto-fallback: if primary fails, tries next available model
- Dashboard shows live badge per model with direct billing links

---

## Features

### F1 — Photo Evaluation (Core)

**Phone UI (`/phone`)**
- Subject selector: Maths / Physics / Chemistry (button group)
- Exam selector: JEE Main / JEE Advanced / ISI / CMI / BITSAT / CBSE Board / General
- Question photo upload — camera capture or gallery, multiple photos supported
- Answer photo upload — camera capture or gallery, multiple pages supported
- Problem number field (e.g. "3, 7") — improves AI detection accuracy, prominently labelled
- Immediate acknowledgement on submit — student does not wait on phone

**AI Processing (background thread)**
- All images sent together with subject + exam context
- AI reads question verbatim, identifies problem numbers, evaluates solution
- Returns per-problem structured JSON with:
  - `question_text` — exact question with LaTeX math
  - `correct_answer` — step-by-step correct solution with LaTeX
  - `topic`, `subtopic`
  - `correctness` — 0–5 integer score
  - `what_went_right`, `where_it_broke`, `mistakes[]`
  - `missing_concept`, `next_practice`, `encouragement`
  - `source` — detected book/paper if visible in photo (HC Verma, NCERT, JEE 2024…)
- JSON parse retry on failure (re-prompts AI for clean JSON only)
- Saved to SQLite with images list, batch ID, timestamp

**Dashboard — Results Tab**
- Auto-polls server every 3 seconds
- Accumulates all questions within the page session (not replaced on each new batch)
- Resets only on page refresh or app restart
- Session summary bar: total questions, solid / almost / needs-work counts
- Per-question collapsible card:
  - Score dots (green ≥4 / yellow =3 / red ≤2)
  - Topic, subtopic, source badge
  - Status pill: Nailed it / Almost there / Needs work
  - Expanded: question text, what went right, where it slipped, mistake tags, brush-up concept, try-next suggestion, encouragement
  - Correct answer — hidden by default, tap/click to reveal
  - "Discuss with mentor" button — opens inline Socratic chat
- Hint button — sends question photos to AI for 3 progressive hints (no answer given)

---

### F2 — Socratic Debate (Per Question)

- Inline chat panel per evaluated question in Results tab
- AI acts as Socratic mentor: never gives the answer, asks probing questions
- Full evaluation context injected: question, score, what went wrong, what went right
- Conversation history maintained within session (up to 20 turns)
- Prompt rules: max 3 sentences + 1 question per turn; no generic praise; explicitly admits if student makes a valid point
- **Auto Wow Note**: AI silently checks each exchange for a clear insight worth saving — auto-saves if found (background thread, zero latency impact)
- Manual Wow Note: student types their own insight and saves it

---

### F3 — Voice Mentor

- Live voice session via Gemini 2.5 Flash Native Audio (voice: Puck)
- WebSocket relay: browser ↔ Flask ↔ Gemini Live API
- Student dossier (weak topics, strong topics, recent session, common mistakes) injected as system prompt
- Style: warm, casual, 2–3 sentences per response, one follow-up question, no LaTeX spoken aloud
- Capabilities: formula drills, topic explanations, session review by question number, exam strategy, study-buddy chat
- Audio protocol: browser sends PCM16 16kHz → server → Gemini; receives PCM16 24kHz back

---

### F4 — History Tab

- All evaluations stored permanently, newest first, up to 200 shown
- Columns: Date · Subject · Exam · Problem # · Topic · Score
- Sortable by Date / Topic / Score (▲▼ toggle on column header)
- Click any row → modal with full detail: question text, what went right, where it slipped, brush-up concept, correct answer reveal, encouragement

---

### F5 — Progress Tab

- Overall: total questions attempted, average score
- By subject: count + average score
- By exam: count + average score
- Weakest topics: bottom 8 by average score
- Strongest topics: top 5 with average ≥ 4/5
- Common mistakes: top 5 recurring mistake tags across all evaluations
- 14-day trend chart: questions per day + average score line

---

### F6 — Practice Problems

- Generate a fresh problem on demand: subject, topic, difficulty (easy / medium / hard), exam type
- AI generates: problem statement with LaTeX, 3 progressive hints (vague → specific → nearly gives away)
- Weak topics auto-suggested as default
- Saved to DB (`practice_problems` table)

---

### F7 — Concept Explainer

- Input: topic name + subject + exam target
- AI returns: core concept in plain terms, key formulas, one worked example, common mistakes, connections to other topics

---

### F8 — Wow Notes

- Personal learning library
- Sources: auto-extracted from debate exchanges + manual student entries
- Displayed newest first, tagged by subject/topic
- Wow Notes tab on dashboard

---

### F9 — Exam Calendar

- 10 pre-loaded exams: CBSE Board, JEE Main (Jan + Apr), JEE Advanced, BITSAT, ISI, CMI, IIIT-H, TNEA, IISER
- Per exam: registration open/close, exam dates, result date, official URL, apply URL, notes
- Dynamic status: Upcoming / Registration Open / Exam Soon / Results Due / Past
- AI verification on demand: cross-checks dates against live web via Perplexity — returns `confirmed` / `approximate` / `wrong` / `not_announced`

---

### F10 — College Admission Guide

- Pre-generated reference guide for JEE 2027 college admissions
- In-app HTML reader, PDF download, print view
- Source file: `data/guide_content.html` — regenerated by `generate_guide.py`

---

### F11 — Auto-Update

- On every restart: fetches `origin/main`, compares hash against `data/.last_code_update`
- If new code: checks out code files only (`data/` never touched), runs pip install, restarts via `os.execv`
- If pip fails: reverts code files, retries on next restart
- Code files tracked: `app.py`, `db.py`, `models.py`, `setup.sh`, `requirements.txt`, `mathtutor.py`, `generate_guide.py`, `templates/`

---

### F12 — Auto-Backup to GitHub

- Trigger 1: debounced 120 seconds after last evaluation completes
- Trigger 2: on every app restart (before auto-update restart)
- Trigger 3: daily background thread (every 24 hours)
- Exports: all evaluations, practice problems, wow notes, debate logs + last 200 app log lines
- Git flow: `add data/` → `commit "backup: YYYY-MM-DD HH:MM"` → `pull --rebase` → `push`

---

## Data Model (SQLite — `tutor.db`)

| Table | Key Columns |
|---|---|
| `evaluations` | batch_id, timestamp, subject, exam, problem_number, question_text, correct_answer, source, topic, subtopic, correctness, what_went_right, where_it_broke, mistakes, missing_concept, hint, next_practice, encouragement, question_images, answer_images |
| `practice_problems` | timestamp, subject, exam, topic, difficulty, problem_text, hints, attempted |
| `wow_notes` | timestamp, subject, topic, note, source |
| `debate_logs` | timestamp, subject, topic, question_text, student_message, mentor_reply |

---

## Known Limitations

| Item | Notes |
|---|---|
| Claude no credits | Top up at console.anthropic.com — auto-resumes on next evaluation |
| Photo detection accuracy | AI vision limitation — problem number field is primary mitigation |
| Double backup on restart | auto_update backs up then restart backs up again — harmless, low priority |
| Voice mentor | Requires Gemini Live API access enabled in Google AI Studio |
| Math rendering | KaTeX renders LaTeX in dashboard; very complex expressions may not display perfectly |
| History limit | Returns most recent 200 evaluations |

---

## Change Log

| Version | Date | Summary |
|---|---|---|
| 1.0 | 2026-04-19 | Initial requirements document — reflects live system state |
