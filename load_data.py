"""
Load sample data into SQLite, then run real PaddleOCR on sample sheets.

  sample_data/results.csv
  sample_data/answers_mcq_dbms.csv
  sample_data/S030.jpg, S047.jpg, S052.jpg  → real OCR

Run:  python load_data.py
"""
import os
import pandas as pd
from db import init, conn

HERE = os.path.dirname(os.path.abspath(__file__))
SD = os.path.join(HERE, "sample_data")


def load():
    init()
    c = conn()

    results = pd.read_csv(os.path.join(SD, "results.csv"))
    exams = (
        results[["subject", "exam_date", "difficulty"]]
        .drop_duplicates()
        .sort_values(["exam_date", "subject"])
        .reset_index(drop=True)
    )
    exam_ids = {}
    for i, row in exams.iterrows():
        eid = i + 1
        exam_ids[(row["subject"], row["exam_date"])] = eid
        c.execute(
            "INSERT INTO exams VALUES (?,?,?,?,?)",
            (eid, row["subject"], "external", row["exam_date"], row["difficulty"]),
        )

    students = sorted(results["student_id"].unique())
    for sid in students:
        c.execute(
            "INSERT INTO students VALUES (?,?,?,?)",
            (sid, f"Student {sid[1:]}", "AI&DS", 2),
        )

    for _, r in results.iterrows():
        eid = exam_ids[(r["subject"], r["exam_date"])]
        c.execute(
            "INSERT INTO marks(student_id,exam_id,marks,internal_marks) VALUES (?,?,?,?)",
            (r["student_id"], eid, float(r["marks"]), float(r["internal_marks"])),
        )

    mcq_path = os.path.join(SD, "answers_mcq_dbms.csv")
    if os.path.isfile(mcq_path):
        mcq = pd.read_csv(mcq_path)
        for _, r in mcq.iterrows():
            key = (r["subject"], r["exam_date"])
            if key not in exam_ids:
                continue
            eid = exam_ids[key]
            c.execute(
                "INSERT INTO answers(student_id,exam_id,question_no,response) VALUES (?,?,?,?)",
                (r["student_id"], eid, int(r["question_no"]), str(r["response"]).strip()),
            )

    c.commit()
    c.close()

    print(f"Loaded {len(students)} students, {len(exams)} exams, {len(results)} mark rows.")
    print("Exam map:", {f"{s} ({d})": i for (s, d), i in exam_ids.items()})

    # Real PaddleOCR on handwritten sheets for Data Structures
    ds_key = None
    for (sub, date), eid in exam_ids.items():
        if "Data" in str(sub):
            ds_key = eid
            break

    if ds_key is None:
        print("No Data Structures exam — skip OCR")
        return

    print(f"Running PaddleOCR on sample sheets (exam_id={ds_key})...")
    try:
        from ocr_utils import ocr_sheet_to_db

        for fname in ("S030.jpg", "S047.jpg", "S052.jpg"):
            path = os.path.join(SD, fname)
            if not os.path.isfile(path):
                print(f"  missing {fname}")
                continue
            sid = os.path.splitext(fname)[0]
            try:
                ans = ocr_sheet_to_db(path, sid, ds_key)
                preview = " | ".join(f"Q{q}:{a[:40]}" for q, a in sorted(ans.items()))
                print(f"  OCR {sid}: {len(ans)} answers — {preview}")
            except Exception as e:
                print(f"  OCR {sid} FAILED: {e}")
    except Exception as e:
        print(f"PaddleOCR error: {e}")
        print("Fix: pip install paddlepaddle==2.6.2 paddleocr==2.7.3 opencv-python-headless")
        print("     sudo apt-get install -y libgomp1 libgl1 libglib2.0-0")
        print("     export FLAGS_use_mkldnn=0")


if __name__ == "__main__":
    load()
