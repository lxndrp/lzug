-- Preserve the existing round links as assignment history while allowing a
-- candidate to move between committee rounds in the same exam half-year.
BEGIN TRANSACTION;

ALTER TABLE round_candidate
  ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1));

CREATE TABLE candidate_committee_assignment (
  id INTEGER PRIMARY KEY,
  candidate_id INTEGER NOT NULL REFERENCES candidate(id) ON DELETE RESTRICT,
  exam_half_year_id INTEGER NOT NULL REFERENCES exam_half_year(id) ON DELETE RESTRICT,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE RESTRICT,
  round_candidate_id INTEGER NOT NULL REFERENCES round_candidate(id) ON DELETE RESTRICT,
  assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ended_at TEXT,
  change_reason TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (ended_at IS NULL OR ended_at >= assigned_at)
);

-- A legacy database may contain the same candidate in several committee rounds
-- of a half-year without enough information to reconstruct each transfer. The
-- highest existing round-candidate ID remains active; older rows stay visible
-- as explicitly marked migration history.
INSERT INTO candidate_committee_assignment (
  candidate_id,
  exam_half_year_id,
  exam_round_id,
  round_candidate_id,
  assigned_at,
  ended_at,
  change_reason
)
SELECT
  round_candidate.candidate_id,
  exam_round.exam_half_year_id,
  round_candidate.exam_round_id,
  round_candidate.id,
  round_candidate.created_at,
  CASE
    WHEN EXISTS (
      SELECT 1
      FROM round_candidate AS newer_round_candidate
      JOIN exam_round AS newer_exam_round
        ON newer_exam_round.id = newer_round_candidate.exam_round_id
      WHERE newer_round_candidate.candidate_id = round_candidate.candidate_id
        AND newer_exam_round.exam_half_year_id = exam_round.exam_half_year_id
        AND newer_round_candidate.id > round_candidate.id
    ) THEN round_candidate.updated_at
    ELSE NULL
  END,
  CASE
    WHEN EXISTS (
      SELECT 1
      FROM round_candidate AS newer_round_candidate
      JOIN exam_round AS newer_exam_round
        ON newer_exam_round.id = newer_round_candidate.exam_round_id
      WHERE newer_round_candidate.candidate_id = round_candidate.candidate_id
        AND newer_exam_round.exam_half_year_id = exam_round.exam_half_year_id
        AND newer_round_candidate.id > round_candidate.id
    ) THEN 'Historische Zuordnung aus Migration; Nachfolger nicht überliefert.'
    ELSE NULL
  END
FROM round_candidate
JOIN exam_round ON exam_round.id = round_candidate.exam_round_id;

UPDATE round_candidate
SET is_active = 0
WHERE id IN (
  SELECT round_candidate_id
  FROM candidate_committee_assignment
  WHERE ended_at IS NOT NULL
);

CREATE UNIQUE INDEX candidate_committee_assignment_one_active_per_half_year
  ON candidate_committee_assignment(candidate_id, exam_half_year_id)
  WHERE ended_at IS NULL;

CREATE INDEX candidate_committee_assignment_history
  ON candidate_committee_assignment(candidate_id, exam_half_year_id, assigned_at DESC);

INSERT INTO schema_migration (name) VALUES ('004_add_candidate_committee_assignments.sql');
COMMIT;
