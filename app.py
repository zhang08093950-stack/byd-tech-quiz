#!/usr/bin/env python3
"""
BYD Tech Quiz — EN/ES bilingual questionnaire.
Uses Turso (hosted SQLite) — shared database for Render and local.
Supports ?lang=en | ?lang=es parameter (default: en).
"""

import random, os, json, logging
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from flask import Flask, render_template, jsonify, request, g

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Turso config ──
TURSO_URL = os.environ.get("TURSO_URL",
    "https://byd-tech-quiz-xinpeng.aws-us-east-1.turso.io/v2/pipeline")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")
if not TURSO_TOKEN:
    # Fallback: read from local token file
    token_file = os.path.expanduser("~/.turso_token")
    if os.path.exists(token_file):
        with open(token_file) as f:
            TURSO_TOKEN = f.read().strip()

_BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_BASE, "templates"))

LANGS = {"en": "English", "es": "Español"}
ANSWER_LETTERS = ['a', 'b', 'c', 'd', 'e']


# ── Turso HTTP helpers ──

def _turso_request(sql, params=None):
    """Execute SQL statement(s) via Turso HTTP pipeline API. Returns parsed JSON."""
    stmt = {"sql": sql}
    if params:
        stmt["args"] = []
        for p in params:
            if isinstance(p, str):
                stmt["args"].append({"type": "text", "value": p})
            elif isinstance(p, (int, float)):
                stmt["args"].append({"type": "integer", "value": str(p)})
            elif p is None:
                stmt["args"].append({"type": "null"})
            else:
                stmt["args"].append({"type": "text", "value": str(p)})

    body = json.dumps({"requests": [{"type": "execute", "stmt": stmt}]}).encode()
    req = Request(TURSO_URL, data=body, headers={
        "Authorization": f"Bearer {TURSO_TOKEN}",
        "Content-Type": "application/json",
    })
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _turso_execute(sql, params=None):
    """Execute a single SQL statement, return list of dicts."""
    result = _turso_request(sql, params)
    response = result["results"][0]
    if response["type"] != "ok":
        raise RuntimeError(f"Turso error: {response}")
    exec_result = response["response"]["result"]
    cols = [c["name"] for c in exec_result.get("cols", [])]
    rows = []
    for row in exec_result.get("rows", []):
        d = {}
        for i, col in enumerate(cols):
            v = row[i]
            if v["type"] == "null":
                d[col] = None
            elif v["type"] == "integer":
                d[col] = int(v.get("value", "0"))
            else:
                d[col] = v.get("value", "")
        rows.append(d)
    return rows


def _turso_batch(statements):
    """Execute multiple SQL statements in one pipeline request."""
    body = {"requests": []}
    for sql, params in statements:
        stmt = {"sql": sql}
        if params:
            stmt["args"] = [{"type": "text", "value": str(p)} if isinstance(p, str)
                           else {"type": "integer", "value": str(p)} for p in params]
        body["requests"].append({"type": "execute", "stmt": stmt})

    req = Request(TURSO_URL, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {TURSO_TOKEN}",
        "Content-Type": "application/json",
    })
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ── Question building ──

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

    answer_raw = (row.get("answer") or "").strip().lower()
    is_multi = ',' in answer_raw

    if is_multi:
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

    correct_en_texts = [options_en[i] for i in correct_indexes]
    correct_es_texts = [options_es[i] for i in correct_indexes]

    return {
        "question_en": row.get("question", ""),
        "question_es": row.get("question_es", "") or row.get("question", ""),
        "options_en": options_en,
        "options_es": options_es,
        "correct_index": correct_index,
        "correct_indexes": correct_indexes,
        "multi": is_multi,
        "explanation_en": "Correct: " + "; ".join(correct_en_texts),
        "explanation_es": "Correcto: " + "; ".join(correct_es_texts),
        "category": row.get("category", "technician"),
    }


# ── Routes ──

@app.before_request
def set_lang():
    lang = request.args.get("lang", "en")
    if lang not in LANGS:
        lang = "en"
    g.lang = lang


@app.context_processor
def inject_lang():
    return {"lang": g.lang, "langs": LANGS}


# ── Auto-cleanup Turso history ──
MAX_HISTORY_ROWS = 500  # keep at most this many rows in Turso history


def _cleanup_turso_history():
    """Delete oldest history rows if Turso exceeds MAX_HISTORY_ROWS."""
    try:
        rows = _turso_execute("SELECT COUNT(*) as cnt FROM tech__quiz_history")
        count = rows[0]["cnt"]
        if count <= MAX_HISTORY_ROWS:
            return

        # Delete oldest sessions beyond the limit
        to_delete = count - MAX_HISTORY_ROWS
        _turso_execute(
            """DELETE FROM tech__quiz_history WHERE id IN (
                   SELECT id FROM tech__quiz_history ORDER BY id ASC LIMIT ?)""",
            [to_delete],
        )
        logger.info(f"Turso cleanup: deleted {to_delete} old history rows")
    except Exception as e:
        logger.warning(f"Turso cleanup failed (non-fatal): {e}")


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
    try:
        rows = _turso_execute("SELECT COUNT(*) as cnt FROM tech__quiz_bank")
        return jsonify({"db": "turso", "questions": rows[0]["cnt"]})
    except Exception as e:
        return jsonify({"db": "turso", "error": str(e)}), 500


@app.route("/api/questions")
def api_questions():
    """Return 5 random questions from tech__quiz_bank."""
    try:
        # Get all rowids to sample from (avoids gap issues with deleted rows)
        all_rows = _turso_execute("SELECT rowid FROM tech__quiz_bank")
        if not all_rows:
            return jsonify({"questions": []})

        rowids = [r["rowid"] for r in all_rows]
        count = len(rowids)
        sample_size = min(5, count)
        selected = random.sample(rowids, sample_size)

        # Fetch exactly the selected rows
        placeholders = ",".join(["?" for _ in selected])
        rows = _turso_execute(
            f"SELECT * FROM tech__quiz_bank WHERE rowid IN ({placeholders})",
            selected,
        )
        questions = [_build_question(r) for r in rows]
        random.shuffle(questions)
        return jsonify({"questions": questions})
    except Exception as e:
        logger.error(f"Questions error: {e}")
        return jsonify({"error": "Failed to load questions"}), 500


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """Save a quiz session's answers."""
    data = request.get_json()
    session_id = data.get("session_id", "")
    answers = data.get("answers", [])

    if not session_id or not answers:
        return jsonify({"ok": False, "error": "Missing session_id or answers"}), 400

    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        batch = []
        for a in answers:
            batch.append((
                """INSERT INTO tech__quiz_history
                   (session_id, question_type, question_en, question_es, options,
                    correct_index, chosen_index, is_correct, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    session_id,
                    a.get("category", ""),
                    a.get("question_en", ""),
                    a.get("question_es", ""),
                    json.dumps(a.get("options", []), ensure_ascii=False),
                    a.get("correct_index"),
                    a.get("chosen_index"),
                    1 if a.get("is_correct") else 0,
                    now,
                ],
            ))
        _turso_batch(batch)
        # Auto-clean old history to keep Turso lean
        _cleanup_turso_history()
        return jsonify({"ok": True, "saved": len(answers)})
    except Exception as e:
        logger.error(f"Submit error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
def api_history():
    """Return recent quiz sessions with stats."""
    limit = request.args.get("limit", 10, type=int)
    try:
        # Single query: join session summary with all details
        rows = _turso_execute(
            """SELECT h.id, h.session_id, h.question_type, h.question_en,
                      h.question_es, h.options, h.correct_index,
                      h.chosen_index, h.is_correct, h.created_at
               FROM tech__quiz_history h
               JOIN (
                   SELECT session_id, MAX(created_at) as max_time
                   FROM tech__quiz_history
                   GROUP BY session_id
                   ORDER BY max_time DESC
                   LIMIT ?
               ) s ON h.session_id = s.session_id
               ORDER BY s.max_time DESC, h.session_id, h.id""",
            [limit],
        )

        # Group by session_id in Python
        sessions_map = {}
        for row in rows:
            sid = row["session_id"]
            if sid not in sessions_map:
                sessions_map[sid] = {
                    "session_id": sid,
                    "time": row["created_at"],
                    "questions": [],
                }
            sessions_map[sid]["questions"].append({
                "question_type": row["question_type"],
                "question_en": row["question_en"],
                "question_es": row["question_es"],
                "options": json.loads(row["options"]) if row["options"] else [],
                "correct_index": row["correct_index"],
                "chosen_index": row["chosen_index"],
                "is_correct": row["is_correct"] == 1,
            })

        for s in sessions_map.values():
            s["total"] = len(s["questions"])
            s["correct"] = sum(1 for q in s["questions"] if q["is_correct"])

        result = list(sessions_map.values())
        # Re-sort by time descending
        result.sort(key=lambda x: x["time"] or "", reverse=True)
        return jsonify({"history": result})
    except Exception as e:
        logger.error(f"History error: {e}")
        return jsonify({"history": []})


if __name__ == "__main__":
    print("BYD Tech Quiz — http://localhost:8790", flush=True)
    app.run(host="0.0.0.0", port=8790, debug=True)
