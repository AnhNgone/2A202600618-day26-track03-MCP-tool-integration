"""Create and seed the lab SQLite database with a reproducible dataset."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "lab.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    cohort TEXT NOT NULL,
    enrolled_on TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    credits INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    term TEXT NOT NULL,
    score REAL
);
"""

SEED_SQL = """
INSERT INTO students (name, email, cohort, enrolled_on) VALUES
    ('Alice Nguyen', 'alice@example.com', 'A1', '2025-01-10'),
    ('Bao Tran', 'bao@example.com', 'A1', '2025-01-10'),
    ('Chi Le', 'chi@example.com', 'A2', '2025-01-12'),
    ('Duy Pham', 'duy@example.com', 'A2', '2025-01-12'),
    ('Emi Vu', 'emi@example.com', 'B1', '2025-02-01');

INSERT INTO courses (title, department, credits) VALUES
    ('Intro to Python', 'CS', 3),
    ('Databases 101', 'CS', 4),
    ('Linear Algebra', 'MATH', 3);

INSERT INTO enrollments (student_id, course_id, term, score) VALUES
    (1, 1, '2025-S1', 92.5),
    (1, 2, '2025-S1', 88.0),
    (2, 1, '2025-S1', 76.0),
    (3, 2, '2025-S1', 95.0),
    (3, 3, '2025-S1', 81.5),
    (4, 3, '2025-S1', 69.0),
    (5, 1, '2025-S1', 84.0);
"""


def create_database(db_path=DB_PATH, reset=True):
    """Create the schema and seed data, returning the database path.

    When reset is True (default) any existing database file is dropped first
    so the script is safely repeatable.
    """
    db_path = Path(db_path)
    if reset and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        if reset:
            conn.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()

    return str(db_path)


if __name__ == "__main__":
    path = create_database()
    print(f"Database created at {path}")
