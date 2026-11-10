# Exam Result Anomaly Detection for Malpractice

**Login:** teacher / teacher123

## Your real sample data (included)

| File | Contents |
|------|----------|
| `sample_data/results.csv` | Marks for Maths, Physics, DBMS, Data Structures |
| `sample_data/answers_mcq_dbms.csv` | MCQ answers (A/B/C/D) for DBMS |
| `sample_data/S030.jpg` `S047.jpg` `S052.jpg` | Handwritten answer sheets for OCR |

Notable patterns in this data:
- **S047** — Data Structures external **93** on a hard paper (class mostly 30–70) → spike + hard-paper outlier; sheet text nearly matches **S052**
- **S019** — Physics internal **22** vs external **66** → large gap

## Setup

```bash
cd ~/exam_anomaly_v2
source venv/bin/activate   # or create: python3.11 -m venv venv && pip install -r requirements.txt

python load_data.py        # loads CSVs + tries OCR on the three images
python app.py
```

If OCR fails during `load_data.py` (Paddle not ready), open the site → Upload → run OCR for S047 / S052 / S030 on the **Data Structures** exam.

Then: **Run Analysis** → **Flagged Cases**.

## Pipeline

Webpage → SQLite → CSV → HDFS → Spark → Dashboard

## Thresholds (viva)

| Signal | Cutoff | Why |
|--------|--------|-----|
| Score spike | +25 vs own history | ~2 SD of typical personal variation |
| Internal–external gap | 30 marks | Above usual CA vs final spread |
| Answer similarity | cosine ≥ 0.80 | Independent writers rarely that high |
| Hard-paper z-score | z > 2 | Standard outlier rule |

## Delete old project

```bash
rm -rf ~/exam_anomaly
rm -f ~/exam_anomaly_backup.zip
```
