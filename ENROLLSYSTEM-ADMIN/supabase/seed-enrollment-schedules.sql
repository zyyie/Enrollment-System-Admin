-- Default class schedules for enrollment
-- Run after seed-shs-curriculum.sql and enrollment-workflow.sql

ALTER TABLE subjects ADD COLUMN IF NOT EXISTS semester_code TEXT
  CHECK (semester_code IS NULL OR semester_code IN ('1st', '2nd'));

UPDATE subjects SET semester_code = '1st' WHERE code IN ('G11-A01', 'G11-ABM-01', 'G11-ABM-02', 'G11-C01', 'G11-C02', 'G11-C03', 'G11-C04', 'G11-C05', 'G11-CK-01', 'G11-CK-02', 'G11-CK-03', 'G11-CK-04', 'G11-EIM-01', 'G11-EIM-02', 'G11-EIM-03', 'G11-EIM-04', 'G11-HUM-01', 'G11-HUM-02', 'G11-HUM-03', 'G11-ICT-01', 'G11-ICT-02', 'G11-PE1', 'G11-STEM-01', 'G11-STEM-02', 'G11-STEM-03');
UPDATE subjects SET semester_code = '2nd' WHERE code IN ('G11-A02', 'G11-ABM-03', 'G11-ABM-04', 'G11-C06', 'G11-C07', 'G11-C08', 'G11-C09', 'G11-C10', 'G11-CK-05', 'G11-CK-06', 'G11-CK-07', 'G11-CK-08', 'G11-CK-09', 'G11-CK-10', 'G11-CK-11', 'G11-EIM-05', 'G11-EIM-06', 'G11-EIM-07', 'G11-HUM-04', 'G11-HUM-05', 'G11-HUM-06', 'G11-ICT-03', 'G11-ICT-04', 'G11-PE2', 'G11-STEM-04', 'G11-STEM-05', 'G11-STEM-06');
UPDATE subjects SET semester_code = '1st' WHERE code IN ('G12-A01', 'G12-A02', 'G12-A03', 'G12-ABM-01', 'G12-ABM-02', 'G12-C01', 'G12-C02', 'G12-CK-01', 'G12-CK-02', 'G12-CK-03', 'G12-CK-04', 'G12-EIM-01', 'G12-EIM-02', 'G12-EIM-03', 'G12-HUM-01', 'G12-ICT-01', 'G12-ICT-02', 'G12-PE3', 'G12-STEM-01', 'G12-STEM-02');
UPDATE subjects SET semester_code = '2nd' WHERE code IN ('G12-A04', 'G12-A05', 'G12-A06', 'G12-ABM-03', 'G12-ABM-04', 'G12-C03', 'G12-CK-05', 'G12-CK-06', 'G12-CK-07', 'G12-CK-08', 'G12-EIM-04', 'G12-EIM-05', 'G12-HUM-02', 'G12-ICT-03', 'G12-ICT-04', 'G12-PE4', 'G12-STEM-03', 'G12-STEM-04');

INSERT INTO sections (name, strand_id, grade_level)
SELECT build_section_name(str.code, g.gl, slot.slot), str.id, g.gl
FROM strands str
CROSS JOIN (VALUES ('Grade 11'), ('Grade 12')) AS g(gl)
CROSS JOIN (VALUES ('A'), ('B')) AS slot(slot)
WHERE str.is_active = TRUE
ON CONFLICT (name, strand_id, grade_level) DO NOTHING;

INSERT INTO class_schedules (
  subject_id, section_id, semester_id, schedule_label, day_of_week,
  start_time, end_time, max_slots, is_active, is_published
)
SELECT sub.id, sec.id, sem.id, 'MW 9:00AM-10:30AM', 'MW',
  TIME '09:00:00', TIME '10:30:00', 40, TRUE, TRUE
FROM subjects sub
JOIN sections sec ON sec.grade_level = sub.grade_level
  AND (sub.strand_id IS NULL OR sub.strand_id = sec.strand_id)
JOIN strands str ON str.id = sec.strand_id AND str.is_active = TRUE
JOIN semesters sem ON sem.is_current = TRUE
WHERE sub.is_active = TRUE
  AND (sub.semester_code IS NULL OR sub.semester_code = sem.code)
  AND NOT EXISTS (
    SELECT 1 FROM class_schedules cs
    WHERE cs.subject_id = sub.id AND cs.section_id = sec.id AND cs.semester_id = sem.id
  );
