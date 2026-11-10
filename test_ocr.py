"""
Test real PaddleOCR on sample sheets.
Run:  python test_ocr.py
      python test_ocr.py sample_data/S047.jpg
"""
import os
import sys

os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ocr_utils import image_to_text, split_answers


def main():
    args = sys.argv[1:] or [
        os.path.join(HERE, "sample_data", f)
        for f in ("S030.jpg", "S047.jpg", "S052.jpg")
        if os.path.isfile(os.path.join(HERE, "sample_data", f))
    ]
    if not args:
        print("No images found. Put sheets in sample_data/ or pass a path.")
        return 1
    for path in args:
        print("=" * 60)
        print("FILE:", path)
        try:
            text = image_to_text(path)
            print("--- RAW OCR TEXT ---")
            print(text if text else "(empty)")
            ans = split_answers(text)
            print("--- PARSED ANSWERS ---")
            for q in sorted(ans):
                print(f"  Q{q}: {ans[q]}")
            if not ans:
                print("  (none parsed)")
        except Exception as e:
            print("FAILED:", e)
            return 1
    print("=" * 60)
    print("OCR OK — use Upload → Handwritten sheets on the website.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
