#!/usr/bin/env python3
"""
BYD Tech Quiz — EN/ES bilingual questionnaire.
Serves 5 random multiple-choice questions from tech__quiz_bank.
Supports ?lang=en | ?lang=es parameter (default: en).

Local dev: reads from external drive /Volumes/PS2000/BYD/Uruguay/uruguay.db
Render/prod: reads from bundled data/tech_quiz.db
"""

import sqlite3, random, os, json
from flask import Flask, render_template, jsonify, request, g

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
    """Convert a tech__quiz_bank row dict into a quiz question."""
    options_en = []
    options_es = []
    for letter in ANSWER_LETTERS:
        en_val = (row.get(f"option_{letter}") or "").strip()
        es_val = (row.get(f"option_{letter}_es") or "").strip()
        if en_val or es_val:
            options_en.append(en_val)
            options_es.append(es_val)
        else:
            break

    answer_letter = (row.get("answer") or "").strip().lower()
    try:
        correct_index = ANSWER_LETTERS.index(answer_letter)
    except ValueError:
        correct_index = 0

    if correct_index >= len(options_en):
        correct_index = len(options_en) - 1

    question_en = row.get("question", "")
    question_es = row.get("question_es", "") or question_en

    explanation_en = f"The correct answer is: <strong>{options_en[correct_index]}</strong>"
    explanation_es = f"La respuesta correcta es: <strong>{options_es[correct_index]}</strong>"

    return {
        "question_en": question_en,
        "question_es": question_es,
        "options_en": options_en,
        "options_es": options_es,
        "correct_index": correct_index,
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
            created_at TEXT DEFAULT (datetime('now','localtime'))
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
                 correct_index, chosen_index, is_correct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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


if __name__ == "__main__":
    init_db()
    print("BYD Tech Quiz — http://localhost:8790", flush=True)
    app.run(host="0.0.0.0", port=8790, debug=True)
