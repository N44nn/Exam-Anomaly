"""
DB → CSV → HDFS (or local) → Spark → flagged rows back into DB.

Set USE_HDFS=0 to skip Hadoop. Default tries HDFS and falls back to local
if HDFS commands fail, so demos still work.
"""
import os
import sys
import glob
import io
import subprocess
import pandas as pd
from db import conn

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
USE_HDFS = os.environ.get("USE_HDFS", "1") == "1"
HDFS_URL = os.environ.get("HDFS_URL", "hdfs://localhost:9000")
HDFS_DIR = "/exam"


def sh(cmd, timeout=60):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{(r.stderr or '')[-1500:]}")
    return r.stdout


def hdfs_available():
    try:
        subprocess.run(
            ["hdfs", "dfs", "-ls", "/"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def read_flagged_hdfs():
    """Read Spark output from HDFS without hanging on globs."""
    # Prefer getmerge into a local temp file
    local = os.path.join(DATA, "_flagged_from_hdfs.csv")
    try:
        sh(["hdfs", "dfs", "-getmerge", f"{HDFS_DIR}/flagged", local], timeout=30)
        if os.path.isfile(local) and os.path.getsize(local) > 0:
            return pd.read_csv(local)
    except Exception:
        pass
    # Fallback: list part files then cat the first
    try:
        listing = sh(["hdfs", "dfs", "-ls", f"{HDFS_DIR}/flagged"], timeout=15)
        parts = [
            line.split()[-1]
            for line in listing.splitlines()
            if "part-" in line
        ]
        if not parts:
            return pd.DataFrame()
        txt = sh(["hdfs", "dfs", "-cat", parts[0]], timeout=30)
        return pd.read_csv(io.StringIO(txt)) if txt.strip() else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def read_flagged_local():
    files = sorted(glob.glob(f"{DATA}/flagged/part-*.csv"))
    if not files:
        return pd.DataFrame()
    try:
        return pd.read_csv(files[0])
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def run():
    log = []
    os.makedirs(DATA, exist_ok=True)
    c = conn()

    for t in ["marks", "exams", "answers"]:
        pd.read_sql(f"SELECT * FROM {t}", c).to_csv(f"{DATA}/{t}.csv", index=False)
    log.append("1. Exported marks / exams / answers from database → CSV")

    use_hdfs = USE_HDFS and hdfs_available()
    if USE_HDFS and not use_hdfs:
        log.append("2. HDFS not reachable — auto-fallback to local data/ folder")

    if use_hdfs:
        try:
            sh(["hdfs", "dfs", "-mkdir", "-p", HDFS_DIR], timeout=20)
            for t in ["marks", "exams", "answers"]:
                sh(
                    ["hdfs", "dfs", "-put", "-f", f"{DATA}/{t}.csv", f"{HDFS_DIR}/{t}.csv"],
                    timeout=30,
                )
            base = HDFS_URL + HDFS_DIR
            log.append(f"2. Copied CSVs into HDFS at {base}")
            try:
                listing = sh(["hdfs", "dfs", "-ls", HDFS_DIR], timeout=15)
                log.append("   HDFS listing:\n" + listing.strip())
            except Exception:
                pass
        except Exception as e:
            log.append(f"2. HDFS put failed ({e}); falling back to local data/")
            use_hdfs = False
            base = DATA
    else:
        base = DATA
        if not USE_HDFS:
            log.append("2. HDFS disabled (USE_HDFS=0) — using local data/")
        else:
            log.append("2. Using local data/ (HDFS unavailable)")

    # Always also write local CSVs so fallback read works
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "spark_job.py"), base],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if out.returncode != 0:
        # If Spark failed on HDFS path, retry local
        if use_hdfs:
            log.append("3. Spark on HDFS failed — retrying on local data/")
            out = subprocess.run(
                [sys.executable, os.path.join(HERE, "spark_job.py"), DATA],
                capture_output=True,
                text=True,
                timeout=300,
            )
            use_hdfs = False
        if out.returncode != 0:
            raise RuntimeError("Spark failed:\n" + (out.stderr or out.stdout)[-2500:])
    log.append("3. Spark anomaly job finished")
    if out.stdout.strip():
        log.append(out.stdout.strip()[-600:])

    df = pd.DataFrame()
    if use_hdfs:
        df = read_flagged_hdfs()
        if len(df):
            log.append("4. Read flagged results from HDFS")
        else:
            df = read_flagged_local()
            log.append("4. HDFS flagged empty/unreadable — used local data/flagged/")
    else:
        df = read_flagged_local()
        log.append("4. Read flagged results from local data/flagged/")

    c.execute("DELETE FROM flagged")
    if len(df):
        df.to_sql("flagged", c, if_exists="append", index=False)
    c.commit()
    c.close()
    log.append(f"5. Loaded {len(df)} flagged cases into the dashboard database")
    return log


if __name__ == "__main__":
    print("\n".join(run()))
