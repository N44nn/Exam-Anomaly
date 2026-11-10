"""Real PaddleOCR helpers + domain OCR typo cleanup."""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "ocr_worker.py")

_WORD_FIX = {
    "furst": "first", "frst": "first", "flrst": "first",
    "follws": "follows", "folows": "follows", "folow": "follows",
    "lnary": "binary", "hnary": "binary", "blnary": "binary", "binarv": "binary",
    "erery": "every", "enery": "every",
    "sungle": "single", "sngle": "single", "sinale": "single",
    "chuldren": "children", "chilren": "children", "childen": "children",
    "deyueue": "dequeue", "deyueue": "dequeue", "bnary": "binary", "srgle": "single",
    "srgle": "single", "stackis": "stack is", "furst": "first",
    "deueue": "dequeue", "dequeu": "dequeue",
    "enqueu": "enqueue", "enqeue": "enqueue",
    "queve": "queue", "quene": "queue",
    "stac": "stack", "staek": "stack",
    "orden": "order", "ordar": "order", "oder": "order",
    "ard": "and", "un": "in",  # careful: only as whole word
    "hierachy": "hierarchy", "heirarchy": "hierarchy",
    "structre": "structure", "remved": "removed",
}


def _correct_text(s: str) -> str:
    def repl(m):
        w = m.group(0)
        key = w.lower()
        # don't replace short "un"/"in" mid-sentence wrongly — only known typos
        if key in _WORD_FIX and not (key == "un" and False):
            fixed = _WORD_FIX[key]
            if key == "un":
                # only "un first" pattern handled below
                return w
            if w[0].isupper():
                return fixed.capitalize()
            return fixed
        return w

    s = re.sub(r"[A-Za-z]+", repl, s)
    s = re.sub(r"\bun\s+first\b", "in first", s, flags=re.I)
    s = re.sub(r"\bn\s+first\b", "in first", s, flags=re.I)
    s = re.sub(r"\bfirst\s+n\s+first\b", "first in first", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+\.", ".", s)
    # drop trailing OCR noise after a clear sentence end
    for end in ("node", "nodes", "pop", "dequeue", "rear", "first"):
        m = re.search(rf"(?i)^(.*\b{end}\b)\.?\s*", s)
        if m and len(m.group(1)) > 20:
            s = m.group(1)
            if not s.endswith("."):
                pass
            break
    return s


def image_to_text(path: str) -> str:
    env = os.environ.copy()
    env["FLAGS_use_mkldnn"] = "0"
    env["CUDA_VISIBLE_DEVICES"] = ""
    env["OMP_NUM_THREADS"] = "1"
    proc = subprocess.run(
        [sys.executable, WORKER, os.path.abspath(path)],
        capture_output=True, text=True, env=env, timeout=300,
    )
    out = (proc.stdout or "").strip()
    data = None
    for line in reversed(out.splitlines()):
        if line.strip().startswith("{"):
            try:
                data = json.loads(line.strip())
                break
            except json.JSONDecodeError:
                continue
    if data is None:
        raise RuntimeError("PaddleOCR failed:\n" + ((proc.stderr or "") + out)[-1000:])
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "OCR failed"))
    return data.get("text") or ""


def split_answers(text: str) -> dict:
    if not text or not text.strip():
        return {}

    # Fix OCR Q-label mistakes BEFORE split
    norm = text
    # Ql / Qi / Q| / Q1 variants → Q1:
    norm = re.sub(r"(?im)(?:^|\n)\s*Q\s*[lI|]\s*[:.)\-]?\s*", "\nQ1: ", norm)
    norm = re.sub(r"(?im)(?:^|\n)\s*Q\s*1\s*[:.)\-]?\s*", "\nQ1: ", norm)
    # Qs / Qz / Q2 (s looks like 2) → Q2:
    norm = re.sub(r"(?im)(?:^|\n)\s*Q\s*[sSzZ2]\s*[:.)\-]?\s*", "\nQ2: ", norm)
    # Q3
    norm = re.sub(r"(?im)(?:^|\n)\s*Q\s*3\s*[:.)\-]?\s*", "\nQ3: ", norm)
    # bare "q2:" lowercase already handled; also "2:" at line start
    norm = re.sub(r"(?im)(?:^|\n)\s*([123])\s*[:.)\-]\s+", r"\nQ\1: ", norm)

    parts = re.split(r"(?im)(?:^|\n)\s*Q\s*([123])\s*:\s*", norm)
    out = {}
    for i in range(1, len(parts), 2):
        qn = int(parts[i])
        body = re.split(r"(?im)(?:^|\n)\s*Q\s*[123]\s*:", parts[i + 1])[0]
        body = _correct_text(body)
        body = re.sub(r"^(?:Qs|Ql|Q)\s+", "", body, flags=re.I).strip(" :.-")
        if body:
            out[qn] = body

    if len(out) < 2:
        # line-based fallback
        lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 5]
        for i, ln in enumerate(lines[:3], start=1):
            ln2 = re.sub(r"(?i)^q\s*[lIsSzZ123]?\s*[:.)\-]?\s*", "", ln).strip()
            if i not in out:
                out[i] = _correct_text(ln2 or ln)
    return out


def ocr_sheet_to_db(path: str, student_id: str, exam_id: int) -> dict:
    from db import conn

    raw = image_to_text(path)
    answers = split_answers(raw)
    if not answers:
        raise RuntimeError("OCR returned no answers.\nRaw:\n" + raw[:500])
    c = conn()
    c.execute("DELETE FROM answers WHERE student_id=? AND exam_id=?", (student_id, exam_id))
    for q, resp in answers.items():
        c.execute(
            "INSERT INTO answers(student_id,exam_id,question_no,response) VALUES (?,?,?,?)",
            (student_id, exam_id, int(q), resp),
        )
    c.commit()
    c.close()
    return answers
