"""
Apache Spark anomaly detection.

Threshold justification (documented for viva):
  SPIKE_T = 25
    A jump of 25+ marks vs the student's own prior average is outside normal
    exam-to-exam variation (typical SD of a student's scores is ~8–12 marks).
    25 ≈ 2+ SDs of personal history → review-worthy spike.

  GAP_T = 30
    Internal vs external difference of 30+ marks is larger than usual
    continuous-assessment vs final spread in many programmes (~10–15).
    Flags possible coaching-only internals or unexplained final jumps.

  SIM_T = 0.80
    Cosine similarity on TF-IDF of full answer text. Independent writers
    on the same paper rarely exceed ~0.5–0.6 with diverse wording.
    0.80+ implies substantial shared phrasing (near-copy territory).

  Z_T = 2.0
    Classic outlier rule: score ≥ 2 standard deviations above the class
    mean on a paper the cohort found hard (labeled hard or low class mean).

Usage: python spark_job.py <hdfs://.../exam | local/data/dir>
"""
import sys
from pyspark.sql import SparkSession, functions as F, Window
from pyspark.sql.types import DoubleType
from pyspark.ml.feature import Tokenizer, HashingTF, IDF, Normalizer

base = sys.argv[1].rstrip("/")
spark = SparkSession.builder.appName("ExamAnomaly").getOrCreate()
spark.sparkContext.setLogLevel("ERROR")

rd = lambda n: spark.read.csv(
    f"{base}/{n}.csv", header=True, inferSchema=True, multiLine=True, escape='"'
)
marks, exams, answers = rd("marks"), rd("exams"), rd("answers")
m = marks.join(exams.select("exam_id", "subject", "difficulty", "exam_date"), "exam_id")

# 1. Score spike (rule-based)
w_prev = (
    Window.partitionBy("student_id")
    .orderBy("exam_date")
    .rowsBetween(Window.unboundedPreceding, -1)
)
m = m.withColumn("prev_avg", F.avg("marks").over(w_prev))
m = m.withColumn("spike", F.coalesce(F.col("marks") - F.col("prev_avg"), F.lit(0.0)))

# 2. Internal vs external gap (rule-based)
m = m.withColumn("gap", F.abs(F.col("marks") - F.col("internal_marks")))

# 3. Performance vs paper difficulty (std dev / z-score)
w_exam = Window.partitionBy("exam_id")
m = (
    m.withColumn("cls_mean", F.avg("marks").over(w_exam))
    .withColumn("cls_std", F.stddev("marks").over(w_exam))
    .withColumn("z", (F.col("marks") - F.col("cls_mean")) / F.col("cls_std"))
)
g_mean = (
    m.groupBy("exam_id").agg(F.avg("marks").alias("a")).agg(F.avg("a")).collect()[0][0]
)
m = m.withColumn(
    "hard_paper",
    (F.col("difficulty") == "hard") | (F.col("cls_mean") < F.lit(g_mean - 5)),
)

# 4. Answer similarity — TF-IDF cosine (descriptive text or MCQ)
# Prefix q-number so MCQ sequences stay aligned: "q1_a q2_c ..."
clean = F.trim(
    F.regexp_replace(F.lower(F.col("response").cast("string")), r"[^a-z0-9\s]", " ")
)
token = F.concat(
    F.lit("q"),
    F.col("question_no").cast("string"),
    F.lit("_"),
    F.regexp_replace(clean, r"\s+", "_"),
)
docs = answers.groupBy("student_id", "exam_id").agg(
    F.concat_ws(" ", F.collect_list(token)).alias("text")
)
tok = Tokenizer(inputCol="text", outputCol="words").transform(docs)
tf = HashingTF(inputCol="words", outputCol="tf", numFeatures=4096).transform(tok)
tfidf = IDF(inputCol="tf", outputCol="tfidf").fit(tf).transform(tf)
vec = (
    Normalizer(inputCol="tfidf", outputCol="v", p=2.0)
    .transform(tfidf)
    .select("student_id", "exam_id", "v")
)

dot = F.udf(lambda x, y: float(x.dot(y)) if x is not None and y is not None else 0.0, DoubleType())
a, b = vec.alias("a"), vec.alias("b")
pairs = a.join(
    b,
    (F.col("a.exam_id") == F.col("b.exam_id"))
    & (F.col("a.student_id") < F.col("b.student_id")),
).select(
    F.col("a.exam_id").alias("exam_id"),
    F.col("a.student_id").alias("s1"),
    F.col("b.student_id").alias("s2"),
    dot("a.v", "b.v").alias("sim"),
)
both = pairs.select(
    "exam_id", F.col("s1").alias("student_id"), F.col("s2").alias("sim_partner"), "sim"
).union(
    pairs.select(
        "exam_id",
        F.col("s2").alias("student_id"),
        F.col("s1").alias("sim_partner"),
        "sim",
    )
)
w_best = Window.partitionBy("exam_id", "student_id").orderBy(F.desc("sim"))
best = (
    both.withColumn("rn", F.row_number().over(w_best))
    .filter("rn = 1")
    .select("exam_id", "student_id", "sim_partner", F.col("sim").alias("max_sim"))
)
m = m.join(best, ["exam_id", "student_id"], "left").fillna({"max_sim": 0.0})

# Thresholds (see module docstring for justification)
SPIKE_T, GAP_T, SIM_T, Z_T = 25.0, 30.0, 0.80, 2.0

m = (
    m.withColumn("sig_spike", F.col("spike") > SPIKE_T)
    .withColumn("sig_gap", F.col("gap") > GAP_T)
    .withColumn("sig_sim", F.col("max_sim") > SIM_T)
    .withColumn("sig_diff", F.col("hard_paper") & (F.col("z") > Z_T))
)

clip = lambda x: F.least(F.greatest(x, F.lit(0.0)), F.lit(1.0))
m = m.withColumn(
    "suspicion_score",
    F.round(
        100
        * (
            0.30 * F.when(F.col("sig_spike"), clip(F.col("spike") / 40)).otherwise(0.0)
            + 0.20 * F.when(F.col("sig_gap"), clip(F.col("gap") / 50)).otherwise(0.0)
            + 0.30
            * F.when(F.col("sig_sim"), clip((F.col("max_sim") - 0.5) / 0.5)).otherwise(0.0)
            + 0.20 * F.when(F.col("sig_diff"), clip(F.col("z") / 3)).otherwise(0.0)
        ),
        1,
    ),
)
m = m.withColumn(
    "risk",
    F.when(F.col("suspicion_score") >= 60, "High")
    .when(F.col("suspicion_score") >= 30, "Medium")
    .otherwise("Low"),
)
m = m.withColumn(
    "signals",
    F.concat_ws(
        "; ",
        F.when(
            F.col("sig_spike"),
            F.concat(
                F.lit("Score Spike (+"),
                F.round("spike", 0).cast("int"),
                F.lit(" vs previous)"),
            ),
        ),
        F.when(
            F.col("sig_sim"),
            F.concat(
                F.lit("Answer Similarity with "),
                F.col("sim_partner"),
                F.lit(" ("),
                F.round(F.col("max_sim") * 100, 0).cast("int"),
                F.lit("%)"),
            ),
        ),
        F.when(F.col("sig_diff"), F.lit("High score on difficult paper")),
        F.when(
            F.col("sig_gap"),
            F.concat(
                F.lit("Large Internal-External Gap ("),
                F.round("gap", 0).cast("int"),
                F.lit(")"),
            ),
        ),
    ),
)

flagged = (
    m.filter(F.col("sig_spike") | F.col("sig_gap") | F.col("sig_sim") | F.col("sig_diff"))
    .select(
        "student_id",
        "exam_id",
        "subject",
        "risk",
        "suspicion_score",
        "signals",
        F.round("spike", 1).alias("spike"),
        F.round("gap", 1).alias("gap"),
        F.round("z", 2).alias("z"),
        F.round("max_sim", 3).alias("max_sim"),
        "sim_partner",
    )
    .orderBy(F.desc("suspicion_score"))
)
flagged.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{base}/flagged")
flagged.show(20, truncate=False)
spark.stop()
