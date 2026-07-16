BEGIN;

ALTER TABLE planning_settings
  ADD COLUMN exclude_public_holidays INTEGER NOT NULL DEFAULT 0
  CHECK (exclude_public_holidays IN (0, 1));

ALTER TABLE planning_settings
  ADD COLUMN holiday_subdivision_code TEXT
  CHECK (
    holiday_subdivision_code IS NULL
    OR holiday_subdivision_code IN (
      'DE-BB', 'DE-BE', 'DE-BW', 'DE-BY', 'DE-HB', 'DE-HE', 'DE-HH', 'DE-MV',
      'DE-NI', 'DE-NW', 'DE-RP', 'DE-SH', 'DE-SL', 'DE-SN', 'DE-ST', 'DE-TH'
    )
  );

INSERT INTO schema_migration (name)
VALUES ('001_add_holiday_planning_settings.sql');

COMMIT;
