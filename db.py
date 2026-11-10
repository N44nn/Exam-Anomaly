"""SQLite helpers — schema matches the project design."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exam.db")


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    c = conn()
    c.executescript(
        """
        DROP TABLE IF EXISTS students;
        DROP TABLE IF EXISTS exams;
        DROP TABLE IF EXISTS marks;
        DROP TABLE IF EXISTS answers;
        DROP TABLE IF EXISTS flagged;

        CREATE TABLE students (
            student_id TEXT PRIMARY KEY,
            name       TEXT,
            department TEXT,
            year       INTEGER
        );
        CREATE TABLE exams (
            exam_id    INTEGER PRIMARY KEY,
            subject    TEXT,
            exam_type  TEXT,
            exam_date  TEXT,
            difficulty TEXT
        );
        CREATE TABLE marks (
            mark_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id     TEXT,
            exam_id        INTEGER,
            marks          REAL,
            internal_marks REAL
        );
        CREATE TABLE answers (
            answer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  TEXT,
            exam_id     INTEGER,
            question_no INTEGER,
            response    TEXT
        );
        CREATE TABLE flagged (
            student_id      TEXT,
            exam_id         INTEGER,
            subject         TEXT,
            risk            TEXT,
            suspicion_score REAL,
            signals         TEXT,
            spike           REAL,
            gap             REAL,
            z               REAL,
            max_sim         REAL,
            sim_partner     TEXT
        );
        """
    )
    c.commit()
    c.close()
