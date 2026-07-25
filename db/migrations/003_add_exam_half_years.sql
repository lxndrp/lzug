-- Group legacy rounds under a global half-year while retaining every round ID
-- and all dependent planning records. Existing names are interpreted as the
-- historic display label; the new season/year fields are the canonical term.
BEGIN TRANSACTION;

CREATE TABLE exam_half_year (
  id INTEGER PRIMARY KEY,
  season TEXT NOT NULL CHECK (season IN ('summer', 'winter')),
  year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'completed', 'archived')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (season, year)
);

-- Legacy names such as "Winter 2026/27" or "Sommer 2027" are mapped to their
-- term. The deterministic fallback keeps arbitrary historic names migratable.
INSERT INTO exam_half_year (season, year, status)
SELECT
  CASE WHEN lower(name) LIKE '%sommer%' THEN 'summer' ELSE 'winter' END,
  CASE
    WHEN instr(name, '20') > 0 THEN CAST(substr(name, instr(name, '20'), 4) AS INTEGER)
    ELSE 2000 + id
  END,
  'active'
FROM exam_round
GROUP BY
  CASE WHEN lower(name) LIKE '%sommer%' THEN 'summer' ELSE 'winter' END,
  CASE
    WHEN instr(name, '20') > 0 THEN CAST(substr(name, instr(name, '20'), 4) AS INTEGER)
    ELSE 2000 + id
  END;

ALTER TABLE exam_round
  ADD COLUMN exam_half_year_id INTEGER REFERENCES exam_half_year(id) ON DELETE RESTRICT;

UPDATE exam_round
SET exam_half_year_id = (
  SELECT exam_half_year.id
  FROM exam_half_year
  WHERE exam_half_year.season = CASE
    WHEN lower(exam_round.name) LIKE '%sommer%' THEN 'summer' ELSE 'winter'
  END
  AND exam_half_year.year = CASE
    WHEN instr(exam_round.name, '20') > 0
      THEN CAST(substr(exam_round.name, instr(exam_round.name, '20'), 4) AS INTEGER)
    ELSE 2000 + exam_round.id
  END
);

CREATE UNIQUE INDEX exam_round_one_committee_per_half_year
  ON exam_round(exam_half_year_id, committee_id);

-- SQLite cannot make a populated column NOT NULL with ALTER TABLE. These
-- triggers retain the same invariant for all post-migration writes.
CREATE TRIGGER exam_round_requires_half_year_on_insert
BEFORE INSERT ON exam_round
WHEN NEW.exam_half_year_id IS NULL
BEGIN
  SELECT RAISE(ABORT, 'exam_half_year_id is required');
END;

CREATE TRIGGER exam_round_requires_half_year_on_update
BEFORE UPDATE OF exam_half_year_id ON exam_round
WHEN NEW.exam_half_year_id IS NULL
BEGIN
  SELECT RAISE(ABORT, 'exam_half_year_id is required');
END;

INSERT INTO schema_migration (name) VALUES ('003_add_exam_half_years.sql');
COMMIT;
