#!/usr/bin/env python3
"""
BYD Tech Quiz — EN/ES bilingual questionnaire.
Serves 5 random multiple-choice questions from tech__quiz_bank.
Supports ?lang=en | ?lang=es parameter (default: en).

Local dev: reads from external drive /Volumes/PS2000/BYD/Uruguay/uruguay.db
Render/prod: reads from bundled data/tech_quiz.db
Dual-write: quiz history → SQLite + Google Sheets (best-effort)
"""

import sqlite3, random, os, json, logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request, g

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets config
QUIZ_SHEET_ID = '12tRJS2js_Cw4rtZQTGylPjTOemq7lRMsPREzAhuL_Ec'
QUIZ_SHEET_TAB = 'Quiz History'
_gsheet_client = None


def _get_gsheet():
    """Lazy-init Google Sheets client (service account)."""
    global _gsheet_client
    if _gsheet_client is not None:
        return _gsheet_client

    import gspread
    from google.oauth2 import service_account

    # Render: read credentials from env var
    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON', '')
    if creds_json:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(creds_json)
            tmp_path = f.name
        creds = service_account.Credentials.from_service_account_file(
            tmp_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets'])
        os.unlink(tmp_path)
    else:
        # Local: read from known path
        key_path = os.path.expanduser('~/.claude/credentials/trusty-mantra-494923-u0-5ae64fce221b.json')
        creds = service_account.Credentials.from_service_account_file(
            key_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets'])

    _gsheet_client = gspread.authorize(creds)
    return _gsheet_client


def _write_to_sheet(session_id, answers):
    """Append quiz answers to Google Sheet (best-effort, never raises)."""
    try:
        gc = _get_gsheet()
        sh = gc.open_by_key(QUIZ_SHEET_ID)
        ws = sh.worksheet(QUIZ_SHEET_TAB)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        total = len(answers)
        correct = sum(1 for a in answers if a.get('is_correct'))
        score_str = f"{correct}/{total}"

        rows = []
        for a in answers:
            rows.append([
                session_id,
                now,
                a.get('question_en', ''),
                a.get('question_es', ''),
                json.dumps(a.get('options', []), ensure_ascii=False),
                a.get('correct_index'),
                a.get('chosen_index'),
                'Yes' if a.get('is_correct') else 'No',
                score_str,
                a.get('category', ''),
            ])

        # Append all rows at once
        ws.append_rows(rows, value_input_option='RAW')
        logger.info(f"Sheets: wrote {len(rows)} rows for session {session_id[:20]}")
    except Exception as e:
        logger.warning(f"Sheets write failed (non-fatal): {e}")

_BASE = os.path.dirname(os.path.abspath(__file__))
_EXT_DB = "/Volumes/PS2000/BYD/Uruguay/uruguay.db"
_LOCAL_DB = os.path.join(_BASE, "data", "tech_quiz.db")


def get_db_path():
    """Use external drive if available (local dev), else bundled copy (Render)."""
    if os.path.exists(_EXT_DB):
        return _EXT_DB
    return _LOCAL_DB


app = Flask(__name__,
    template_folder=os.path.join(_BASE, "templates"))

LANGS = {"en": "English", "es": "Español"}
ANSWER_LETTERS = ['a', 'b', 'c', 'd', 'e']


def _build_question(row):
    """Convert a tech__quiz_bank row dict into a quiz question.
    Supports both single-select (answer='a') and multi-select (answer='a,b,c').
    """
    options_en = []
    options_es = []
    for letter in ANSWER_LETTERS:
        en_val = (row.get(f"option_{letter}") or "").strip()
        es_val = (row.get(f"option_{letter}_es") or "").strip()
        if en_val or es_val:
            options_en.append(en_val)
            options_es.append(es_val)
        else:
            # Skip empty options mid-list (cleared "All of the above" etc.)
            # but don't stop — there may be more options after
            pass

    answer_raw = (row.get("answer") or "").strip().lower()
    is_multi = ',' in answer_raw

    if is_multi:
        # Parse comma-separated answer letters: "a,b,c" → [0, 1, 2]
        correct_indexes = []
        for ch in answer_raw.split(','):
            ch = ch.strip()
            if ch in ANSWER_LETTERS:
                idx = ANSWER_LETTERS.index(ch)
                if idx < len(options_en):
                    correct_indexes.append(idx)
        correct_index = correct_indexes[0] if correct_indexes else 0
    else:
        try:
            correct_index = ANSWER_LETTERS.index(answer_raw)
        except ValueError:
            correct_index = 0
        if correct_index >= len(options_en):
            correct_index = len(options_en) - 1
        correct_indexes = [correct_index]

    question_en = row.get("question", "")
    question_es = row.get("question_es", "") or question_en

    # Build explanation listing all correct options
    correct_en_texts = [options_en[i] for i in correct_indexes]
    correct_es_texts = [options_es[i] for i in correct_indexes]
    explanation_en = "Correct: " + "; ".join(correct_en_texts)
    explanation_es = "Correcto: " + "; ".join(correct_es_texts)

    return {
        "question_en": question_en,
        "question_es": question_es,
        "options_en": options_en,
        "options_es": options_es,
        "correct_index": correct_index,
        "correct_indexes": correct_indexes,
        "multi": is_multi,
        "explanation_en": explanation_en,
        "explanation_es": explanation_es,
        "category": row.get("category", "technician"),
    }


@app.before_request
def set_lang():
    lang = request.args.get("lang", "en")
    if lang not in LANGS:
        lang = "en"
    g.lang = lang


@app.context_processor
def inject_lang():
    return {"lang": g.lang, "langs": LANGS}


@app.after_request
def add_cache_headers(resp):
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/")
def index():
    return render_template("quiz.html")


@app.route("/api/health")
def api_health():
    """Check if Google Sheets integration is working."""
    import sys
    status = {"db": "ok", "sheets": "unknown"}
    # Check if gspread is installed
    try:
        import gspread
        status["gspread_version"] = gspread.__version__
    except ImportError:
        status["gspread_version"] = "NOT INSTALLED"
    try:
        gc = _get_gsheet()
        sh = gc.open_by_key(QUIZ_SHEET_ID)
        ws = sh.worksheet(QUIZ_SHEET_TAB)
        status["sheets"] = "ok"
        status["sheet_rows"] = ws.row_count
    except Exception as e:
        status["sheets"] = f"error: {e}"
    return jsonify(status)


@app.route("/api/questions")
def api_questions():
    """Return 5 random questions from tech__quiz_bank."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM tech__quiz_bank ORDER BY RANDOM() LIMIT 5"
        ).fetchall()
        questions = [_build_question(dict(r)) for r in rows]
        random.shuffle(questions)
        return jsonify({"questions": questions})
    finally:
        conn.close()


def init_db():
    """Ensure tech quiz history table exists."""
    conn = sqlite3.connect(get_db_path())
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tech__quiz_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question_type TEXT,
            question_en TEXT,
            question_es TEXT,
            options TEXT,
            correct_index INTEGER,
            chosen_index INTEGER,
            is_correct INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_tech_quiz_session ON tech__quiz_history(session_id);
    """)
    conn.commit()
    conn.close()


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """Save a quiz session's answers."""
    data = request.get_json()
    session_id = data.get("session_id", "")
    answers = data.get("answers", [])

    if not session_id or not answers:
        return jsonify({"ok": False, "error": "Missing session_id or answers"}), 400

    conn = sqlite3.connect(get_db_path())
    try:
        conn.executemany("""
            INSERT INTO tech__quiz_history
                (session_id, question_type, question_en, question_es, options,
                 correct_index, chosen_index, is_correct, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, [
            (
                session_id,
                a.get("category", ""),
                a.get("question_en", ""),
                a.get("question_es", ""),
                json.dumps(a.get("options", [])),
                a.get("correct_index"),
                a.get("chosen_index"),
                1 if a.get("is_correct") else 0,
            )
            for a in answers
        ])
        conn.commit()
        # Dual-write to Google Sheets (best-effort, non-blocking)
        _write_to_sheet(session_id, answers)
        return jsonify({"ok": True, "saved": len(answers)})
    finally:
        conn.close()


@app.route("/api/history")
def api_history():
    """Return recent quiz sessions with stats."""
    limit = request.args.get("limit", 10, type=int)
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        sessions = conn.execute("""
            SELECT session_id, COUNT(*) as total,
                   SUM(is_correct) as correct,
                   MAX(created_at) as time
            FROM tech__quiz_history
            GROUP BY session_id
            ORDER BY MAX(created_at) DESC
            LIMIT ?
        """, (limit,)).fetchall()

        result = []
        for s in sessions:
            details = conn.execute("""
                SELECT question_type, question_en, question_es, options,
                       correct_index, chosen_index, is_correct
                FROM tech__quiz_history
                WHERE session_id = ?
                ORDER BY id
            """, (s["session_id"],)).fetchall()

            result.append({
                "session_id": s["session_id"],
                "total": s["total"],
                "correct": s["correct"],
                "time": s["time"],
                "questions": [{
                    "question_type": d["question_type"],
                    "question_en": d["question_en"],
                    "question_es": d["question_es"],
                    "options": json.loads(d["options"]) if d["options"] else [],
                    "correct_index": d["correct_index"],
                    "chosen_index": d["chosen_index"],
                    "is_correct": bool(d["is_correct"]),
                } for d in details],
            })

        return jsonify({"history": result})
    finally:
        conn.close()


# Ensure tables exist — runs both at import (gunicorn) and direct (flask dev)
init_db()

if __name__ == "__main__":
    print("BYD Tech Quiz — http://localhost:8790", flush=True)
    app.run(host="0.0.0.0", port=8790, debug=True)
