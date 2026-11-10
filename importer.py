"""
Import teacher data:

1) Results CSV
   student_id, subject, exam_date, internal_marks, marks, difficulty

2) Answers / MCQ CSV
   student_id, subject, exam_date, question_no, response

3) Handwritten answer sheets
   Photos named <roll>.jpg / .png  e.g. S047.jpg
   OCR via PaddleOCR into answers table for a chosen exam
"""
import os
import pandas as pd
from db import conn

RESULTS_TEMPLATE = """student_id,subject,exam_date,internal_marks,marks,difficulty
S001,Maths,2026-01-20,70,68,medium
S002,Maths,2026-01-20,55,60,medium
"""

ANSWERS_TEMPLATE = """student_id,subject,exam_date,question_no,response
S001,DBMS,2026-03-18,1,A
S001,DBMS,2026-03-18,2,C
S002,DBMS,2026-03-18,1,A
S002,DBMS,2026-03-18,2,B
"""


def _ensure_student(c, student_id):
    if not c.execute("SELECT 1 FROM students WHERE student_id=?", (student_id,)).fetchone():
        c.execute(
            "INSERT INTO students VALUES (?,?,?,?)",
            (student_id, f"Student {student_id}", "AI&DS", 2),
        )


def _ensure_exam(c, subject, exam_date, difficulty="medium"):
    row = c.execute(
        "SELECT exam_id FROM exams WHERE subject=? AND exam_date=?",
        (subject, exam_date),
    ).fetchone()
    if row:
        return row[0]
    eid = c.execute("SELECT COALESCE(MAX(exam_id),0)+1 FROM exams").fetchone()[0]
    c.execute(
        "INSERT INTO exams VALUES (?,?,?,?,?)",
        (eid, subject, "external", exam_date, (difficulty or "medium").lower()),
    )
    return eid


def import_results_csv(path_or_file) -> str:
    df = pd.read_csv(path_or_file)
    df.columns = [str(x).strip().lower().replace(" ", "_") for x in df.columns]
    required = {"student_id", "subject", "exam_date", "marks", "internal_marks"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Results CSV missing columns: {missing}")
    if "difficulty" not in df.columns:
        df["difficulty"] = "medium"

    c = conn()
    n = 0
    for _, r in df.iterrows():
        sid = str(r["student_id"]).strip()
        sub = str(r["subject"]).strip()
        date = str(r["exam_date"]).strip().split()[0]
        diff = str(r.get("difficulty", "medium")).strip().lower()
        _ensure_student(c, sid)
        eid = _ensure_exam(c, sub, date, diff)
        c.execute("DELETE FROM marks WHERE student_id=? AND exam_id=?", (sid, eid))
        c.execute(
            "INSERT INTO marks(student_id,exam_id,marks,internal_marks) VALUES (?,?,?,?)",
            (sid, eid, float(r["marks"]), float(r["internal_marks"])),
        )
        n += 1
    c.commit()
    ns = c.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    ne = c.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
    c.close()
    return f"Imported {n} mark rows ({ns} students, {ne} exams)"


def import_answers_csv(path_or_file) -> str:
    df = pd.read_csv(path_or_file)
    df.columns = [str(x).strip().lower().replace(" ", "_") for x in df.columns]
    required = {"student_id", "subject", "exam_date", "question_no", "response"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Answers CSV missing columns: {missing}")

    c = conn()
    n, skipped = 0, 0
    for _, r in df.iterrows():
        sid = str(r["student_id"]).strip()
        sub = str(r["subject"]).strip()
        date = str(r["exam_date"]).strip().split()[0]
        resp = str(r["response"]).strip()
        if not resp or resp.lower() == "nan":
            skipped += 1
            continue
        _ensure_student(c, sid)
        eid = _ensure_exam(c, sub, date)
        q = int(r["question_no"])
        c.execute(
            "DELETE FROM answers WHERE student_id=? AND exam_id=? AND question_no=?",
            (sid, eid, q),
        )
        c.execute(
            "INSERT INTO answers(student_id,exam_id,question_no,response) VALUES (?,?,?,?)",
            (sid, eid, q, resp),
        )
        n += 1
    c.commit()
    c.close()
    msg = f"Imported {n} answer rows"
    if skipped:
        msg += f" ({skipped} empty skipped)"
    return msg


def import_sheets(files, exam_id, upload_dir):
    """
    Bulk OCR: each file named <student_id>.jpg / .png / .jpeg
    e.g. S047.jpg → student S047
    """
    from ocr_utils import ocr_sheet_to_db
    from werkzeug.utils import secure_filename

    out = []
    for f in files:
        if not f or not f.filename:
            continue
        sid = os.path.splitext(os.path.basename(f.filename))[0].strip()
        path = os.path.join(upload_dir, secure_filename(f.filename))
        f.save(path)
        try:
            ans = ocr_sheet_to_db(path, sid, int(exam_id))
            out.append((sid, len(ans)))
        except Exception as e:
            out.append((sid, f"error: {e}"))
    return out
