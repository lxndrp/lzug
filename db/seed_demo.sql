INSERT INTO committee (id, name, occupation)
VALUES (1, 'PA Fachinformatiker Hamburg 1', 'Fachinformatiker/in');

INSERT INTO committee_member
  (id, committee_id, first_name, last_name, member_status, committee_role, representing_side, email, email_verified_at, mobile)
VALUES
  (1, 1, 'Martin', 'König', 'ordinary', 'chair', 'employer', 'martin.koenig@example.de', CURRENT_TIMESTAMP, '+49 170 1234567'),
  (2, 1, 'Dr. Anne', 'Berg', 'ordinary', 'deputy_chair', 'school', 'anne.berg@example.de', CURRENT_TIMESTAMP, '+49 171 2345678'),
  (3, 1, 'Tobias', 'Rehm', 'ordinary', 'member', 'employee', 'tobias.rehm@example.de', CURRENT_TIMESTAMP, '+49 172 3456789'),
  (4, 1, 'Sabine', 'Jahn', 'ordinary', 'member', 'employer', 'sabine.jahn@example.de', CURRENT_TIMESTAMP, '+49 173 4567890'),
  (5, 1, 'Jan', 'Peters', 'deputy', 'member', 'school', 'jan.peters@example.de', NULL, '+49 174 5678901'),
  (6, 1, 'Nina', 'Albrecht', 'deputy', 'member', 'employee', 'nina.albrecht@example.de', CURRENT_TIMESTAMP, '+49 175 6789012'),
  (7, 1, 'Karim', 'Özdemir', 'deputy', 'member', 'employer', 'karim.oezdemir@example.de', NULL, '+49 176 7890123'),
  (8, 1, 'Claudia', 'Mertens', 'deputy', 'member', 'school', 'claudia.mertens@example.de', CURRENT_TIMESTAMP, '+49 177 8901234');

INSERT INTO user_account (id, committee_member_id, email, password_hash)
VALUES (1, 1, 'martin.koenig@example.de', 'demo-password-hash');

INSERT INTO location
  (id, committee_id, name, street, postal_code, city, room)
VALUES
  (1, 1, 'Bildungszentrum HafenCity', 'Am Sandtorkai 42', '20457', 'Hamburg', 'Konferenzraum 3.12'),
  (2, 1, 'Berufliche Schule IT', 'Eulenkamp 46', '22049', 'Hamburg', 'Prüfungsraum B 204');

INSERT INTO candidate
  (id, first_name, last_name, ihk_exam_number, specialization, training_company)
VALUES
  (1, 'Lea', 'Hoffmann', 'FI-2026-1042', 'application_development', 'Nordlicht Digital GmbH'),
  (2, 'Jonas', 'Weber', 'FI-2026-1057', 'system_integration', 'HanseNet Solutions AG'),
  (3, 'Mara', 'Schulz', 'FI-2026-1081', 'data_and_process_analysis', 'Datenspur Analytics GmbH'),
  (4, 'Elias', 'Koch', 'FI-2026-1096', 'digital_networking', 'Elbwerke Technik KG'),
  (5, 'Sofia', 'Richter', 'FI-2026-1113', 'application_development', 'Pixelhafen Software GmbH'),
  (6, 'Noah', 'Bauer', 'FI-2026-1128', 'system_integration', 'Kernsysteme Nord GmbH'),
  (7, 'Mila', 'Wagner', 'FI-2026-1144', 'application_development', 'Cloudkontor AG'),
  (8, 'Finn', 'Krüger', 'FI-2026-1162', 'system_integration', 'Bytebrücke GmbH'),
  (9, 'Amelie', 'Wolf', 'FI-2026-1179', 'data_and_process_analysis', 'Prozessblick GmbH'),
  (10, 'Paul', 'Neumann', 'FI-2026-1190', 'digital_networking', 'Netzraum Solutions KG'),
  (11, 'Lina', 'Schröder', 'FI-2026-1205', 'application_development', 'Codewerft GmbH'),
  (12, 'Emil', 'Hartmann', 'FI-2026-1221', 'system_integration', 'Infrapilot AG');

INSERT INTO exam_round
  (id, committee_id, name, status, availability_deadline, availability_reminder_at, created_by_member_id)
VALUES
  (1, 1, 'Winter 2026/27', 'availability_requested', '2026-10-02 18:00:00', '2026-09-29 18:00:00', 1);

INSERT INTO round_candidate
  (id, exam_round_id, candidate_id, attempt_number, requires_mep)
VALUES
  (1, 1, 1, 1, 0),
  (2, 1, 2, 2, 1),
  (3, 1, 3, 1, 0),
  (4, 1, 4, 3, 0),
  (5, 1, 5, 2, 0),
  (6, 1, 6, 1, 1),
  (7, 1, 7, 3, 1),
  (8, 1, 8, 1, 0),
  (9, 1, 9, 2, 1),
  (10, 1, 10, 1, 0),
  (11, 1, 11, 1, 0),
  (12, 1, 12, 2, 0);

INSERT INTO planning_settings
  (id, exam_round_id, calendar_week_from, calendar_week_to, exams_per_day, max_exam_days_per_week, lunch_break_enabled, default_location_id, updated_by_member_id)
VALUES
  (1, 1, '2026-W47', '2026-W49', 6, 3, 1, 1, 1);

INSERT INTO candidate_exam_day (id, exam_round_id, date)
VALUES
  (1, 1, '2026-11-16'),
  (2, 1, '2026-11-17'),
  (3, 1, '2026-11-18'),
  (4, 1, '2026-11-19'),
  (5, 1, '2026-11-20');

INSERT INTO member_availability
  (exam_round_id, committee_member_id, candidate_exam_day_id, availability, responded_at)
SELECT
  1,
  committee_member.id,
  candidate_exam_day.id,
  CASE
    WHEN committee_member.id IN (5, 7) THEN 'pending'
    WHEN candidate_exam_day.id = 3 AND committee_member.id IN (2, 6) THEN 'afternoon'
    WHEN candidate_exam_day.id = 4 AND committee_member.id IN (3, 8) THEN 'morning'
    ELSE 'full_day'
  END,
  CASE WHEN committee_member.id IN (5, 7) THEN NULL ELSE CURRENT_TIMESTAMP END
FROM committee_member
CROSS JOIN candidate_exam_day
WHERE committee_member.committee_id = 1
  AND candidate_exam_day.exam_round_id = 1;
