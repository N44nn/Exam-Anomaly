"""Real PaddleOCR — try original image first, then enhanced if few lines."""
import sys
import json
import os

os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["FLAGS_allocator_strategy"] = "naive_best_fit"
os.environ["OMP_NUM_THREADS"] = "1"


def load_bgr(path):
    import cv2
    import numpy as np

    img = cv2.imread(path)
    if img is None:
        from PIL import Image

        img = np.array(Image.open(path).convert("RGB"))[:, :, ::-1]
    return img


def upscale(img, target=1600):
    import cv2

    h, w = img.shape[:2]
    if max(h, w) >= target:
        return img
    scale = target / max(h, w)
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def enhance(img):
    import cv2

    img = upscale(img, 1800)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def ocr_image(ocr, img):
    result = ocr.ocr(img, cls=True)
    items = []
    for page in result or []:
        if not page:
            continue
        for box, (text, score) in page:
            if not text or not str(text).strip():
                continue
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            items.append((sum(ys) / 4.0, sum(xs) / 4.0, str(text).strip()))
    items.sort(key=lambda t: (round(t[0] / 20) * 20, t[1]))
    return [t[2] for t in items]


def run_ocr(path):
    from paddleocr import PaddleOCR
    import cv2

    ocr = PaddleOCR(
        use_angle_cls=True,
        lang="en",
        show_log=False,
        use_gpu=False,
        enable_mkldnn=False,
        cpu_threads=2,
        det_db_box_thresh=0.3,
        drop_score=0.3,
    )
    raw = load_bgr(path)
    # Path A: mild upscale only (best for clean sheets like S047)
    lines_a = ocr_image(ocr, upscale(raw, 1600))
    # Path B: contrast enhance (helps faint ink)
    lines_b = ocr_image(ocr, enhance(raw))
    # Pick result with more text / more Q-like labels
    def score(lines):
        t = " ".join(lines).lower()
        s = len(t)
        for token in ("q1", "q2", "q3", "ql", "qs", "stack", "queue", "binary"):
            if token in t:
                s += 50
        return s

    return lines_a if score(lines_a) >= score(lines_b) else lines_b


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: ocr_worker.py <image>"}))
        return 1
    path = sys.argv[1]
    if not os.path.isfile(path):
        print(json.dumps({"ok": False, "error": f"file not found: {path}"}))
        return 1
    try:
        lines = run_ocr(path)
        print(json.dumps({"ok": True, "text": "\n".join(lines), "lines": lines, "n": len(lines)}))
        return 0
    except Exception as e:
        import traceback

        print(json.dumps({"ok": False, "error": str(e), "trace": traceback.format_exc()[-400:]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
