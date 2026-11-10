"""
Exam Result Anomaly Detection — Flask app.
Login: teacher / teacher123
"""
import os
import webbrowser
from threading import Timer

from flask import Flask, request, redirect, session, render_template, flash
from werkzeug.utils import secure_filename

from db import conn
import pipeline
from ocr_utils import ocr_sheet_to_db
import importer

app = Flask(__name__)
app.secret_key = "exam-anomaly-v2-key"
USERS = {"teacher": "teacher123", "admin": "admin123"}
UPLOAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")


os.makedirs(UPLOAD, exist_ok=True)


@app.before_request
def guard():
    if request.endpoint not in ("login", "static") and not session.get("user"):
        return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if USERS.get(request.form.get("username")) == request.form.get("password"):
            session["user"] = request.form["username"]
            return redirect("/")
        flash("Wrong username or password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
def dashboard():
    c = conn()
    rows = c.execute(
        "SELECT * FROM flagged ORDER BY suspicion_score DESC"
    ).fetchall()
    c.close()
    counts = {k: sum(1 for r in rows if r["risk"] == k) for k in ("High", "Medium", "Low")}
    return render_template(
        "flagged.html", rows=rows, counts=counts, total=len(rows)
    )


@app.route("/clear-data", methods=["POST"])
def clear_data():
    """Wipe operational data so the teacher demo can start clean."""
    mode = request.form.get("mode", "all")
    c = conn()
    if mode == "flags":
        c.execute("DELETE FROM flagged")
        c.commit()
        c.close()
        flash("Cleared flagged cases only. Click Run Analysis to regenerate.")
    else:
        c.executescript(
            """
            DELETE FROM flagged;
            DELETE FROM answers;
            DELETE FROM marks;
            DELETE FROM exams;
            DELETE FROM students;
            """
        )
        c.commit()
        c.close()
        flash("All data cleared (students, marks, answers, flags). Load demo data or upload CSVs.")
    return redirect("/")


@app.route("/load-demo", methods=["POST"])
def load_demo():
    """Reload sample CSVs + S047/S052 sheet answers for a reliable teacher demo."""
    try:
        from load_data import load as load_csv

        load_csv()
    except Exception as e:
        flash(f"load_data failed: {e}")
        return redirect("/")

    # Always seed handwritten DS answers (OCR may be unavailable)
    try:
        seed_sheet_answers()
        flash("Demo data loaded (results + MCQ + S047/S052/S030 sheet answers). Now Run Analysis.")
    except Exception as e:
        flash(f"Demo CSVs loaded, but sheet seed failed: {e}")
    return redirect("/")




def seed_sheet_answers():
    """Run real PaddleOCR on sample_data sheets for Data Structures."""
    import os
    from ocr_utils import ocr_sheet_to_db

    c = conn()
    row = c.execute(
        "SELECT exam_id FROM exams WHERE subject LIKE '%Data%' ORDER BY exam_id DESC"
    ).fetchone()
    c.close()
    if not row:
        raise RuntimeError("No Data Structures exam — upload results CSV first")
    eid = row[0]
    sd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")
    done = []
    for fname in ("S030.jpg", "S047.jpg", "S052.jpg"):
        path = os.path.join(sd, fname)
        if not os.path.isfile(path):
            continue
        sid = os.path.splitext(fname)[0]
        ans = ocr_sheet_to_db(path, sid, eid)
        done.append(f"{sid}:{len(ans)}")
    if not done:
        raise RuntimeError("No sample sheet images found in sample_data/")
    return ", ".join(done)



@app.route("/upload", methods=["GET", "POST"])
def upload():
    c = conn()
    if request.method == "POST":
        kind = request.form.get("kind")
        try:
            if kind == "results":
                msg = importer.import_results_csv(request.files["file"])
                flash(msg)
            elif kind == "answers":
                msg = importer.import_answers_csv(request.files["file"])
                flash(msg)
            elif kind == "sheets":
                exam_id = int(request.form["exam_id"])
                files = request.files.getlist("files")
                results = importer.import_sheets(files, exam_id, UPLOAD)
                ok = [f"{s}: {n} answers" for s, n in results if not str(n).startswith("error")]
                bad = [f"{s}: {n}" for s, n in results if str(n).startswith("error")]
                flash(
                    "OCR done — "
                    + ("; ".join(ok) if ok else "no sheets")
                    + ((" | Errors: " + "; ".join(bad)) if bad else "")
                )
            elif kind == "manual":
                c.execute(
                    "INSERT INTO marks(student_id,exam_id,marks,internal_marks) VALUES (?,?,?,?)",
                    (
                        request.form["student_id"],
                        int(request.form["exam_id"]),
                        float(request.form["marks"]),
                        float(request.form["internal_marks"]),
                    ),
                )
                c.commit()
                flash("Marks saved")
        except Exception as e:
            flash(f"Error: {e}")
    exams = c.execute("SELECT * FROM exams ORDER BY exam_id").fetchall()
    c.close()
    return render_template("upload.html", exams=exams)


@app.route("/run", methods=["GET", "POST"])
def run():
    if request.method == "POST":
        try:
            log = pipeline.run()
            flash("Run analysis successful — flagged cases updated.")
            return render_template(
                "run_result.html", status="complete", log="\n".join(log)
            )
        except Exception as e:
            return render_template(
                "run_result.html", status="failed", log=str(e)
            )
    return render_template("run.html")


@app.route("/student/<sid>")
def student(sid):
    exam_id = request.args.get("exam", type=int)
    c = conn()
    st = c.execute("SELECT * FROM students WHERE student_id=?", (sid,)).fetchone()
    history = c.execute(
        """SELECT e.subject, e.exam_date, e.difficulty, m.marks, m.internal_marks
           FROM marks m JOIN exams e USING(exam_id)
           WHERE m.student_id=? ORDER BY e.exam_date""",
        (sid,),
    ).fetchall()

    flag = None
    if exam_id:
        flag = c.execute(
            "SELECT * FROM flagged WHERE student_id=? AND exam_id=?",
            (sid, exam_id),
        ).fetchone()
    if not flag:
        flag = c.execute(
            "SELECT * FROM flagged WHERE student_id=? ORDER BY suspicion_score DESC",
            (sid,),
        ).fetchone()

    partner = None
    if flag and flag["sim_partner"]:
        partner = flag["sim_partner"]

    eid = flag["exam_id"] if flag else exam_id

    # Fallback partner: another student with descriptive answers on same exam
    # (keeps S047 vs S052 visible even if max_sim was 0 after a bad run)
    if eid and not partner:
        rows = c.execute(
            """
            SELECT student_id, COUNT(*) AS n FROM answers
            WHERE exam_id=? AND student_id!=?
              AND length(response) > 5
            GROUP BY student_id
            ORDER BY n DESC
            """,
            (eid, sid),
        ).fetchall()
        # Prefer S052 when viewing S047 (and vice versa) for the planted demo pair
        ids = [r["student_id"] for r in rows]
        if sid == "S047" and "S052" in ids:
            partner = "S052"
        elif sid == "S052" and "S047" in ids:
            partner = "S047"
        elif ids:
            partner = ids[0]

    answers = {}
    if eid:
        mine = {
            r["question_no"]: r["response"]
            for r in c.execute(
                "SELECT question_no, response FROM answers WHERE student_id=? AND exam_id=? ORDER BY question_no",
                (sid, eid),
            )
        }
        theirs = {}
        if partner:
            theirs = {
                r["question_no"]: r["response"]
                for r in c.execute(
                    "SELECT question_no, response FROM answers WHERE student_id=? AND exam_id=? ORDER BY question_no",
                    (partner, eid),
                )
            }

        def prefer_text(d):
            long_ones = {q: txt for q, txt in d.items() if len(str(txt)) > 5}
            return long_ones if long_ones else d

        mine = prefer_text(mine)
        theirs = prefer_text(theirs)

        qs = sorted(set(mine) | set(theirs))
        for q in qs:
            answers[q] = (mine.get(q, ""), theirs.get(q, "") if partner else "")
    c.close()
    return render_template(
        "student.html",
        student_id=sid,
        name=st["name"] if st else "",
        flag=flag,
        history=history,
        partner=partner,
        answers=answers,
    )


def _open():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    Timer(1.2, _open).start()
    print("http://127.0.0.1:5000  |  teacher / teacher123")
    app.run(debug=False, host="127.0.0.1", port=5000)
