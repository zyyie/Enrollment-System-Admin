-- ============================================================
-- SEED: Strands, Professors, Subjects (connected by track)
-- Run in Supabase SQL Editor AFTER schema.sql and faculty-strands-rooms.sql
-- ============================================================

-- ── 1. STRANDS (Track → Specialization) ─────────────────────
-- Subject catalog: run seed-shs-curriculum.sql after this file
INSERT INTO strands (code, name, track) VALUES
  ('STEM',    'STEM - Science, Technology, Engineering, and Mathematics', 'Academic'),
  ('ABM',     'Accountancy, Business & Management',                       'Academic'),
  ('HUMSS',   'Humanities & Social Sciences',                             'Academic'),
  ('ICT',     'Information and Communications Technology',                'TechPro'),
  ('COOKERY', 'Cookery',                                                  'TechPro'),
  ('EIM',     'Electrical Installation and Maintenance',                  'TechPro')
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  track = EXCLUDED.track,
  is_active = TRUE;

UPDATE strands SET is_active = FALSE WHERE code IN ('CSS', 'HE', 'INDARTS', 'OTHER', 'GAS');

-- ── 2. PROFESSORS (role = Teacher) ──────────────────────────
INSERT INTO faculty (faculty_id, last_name, first_name, middle_name, role, department, password, max_load_units, is_active) VALUES
  ('FAC-STEM-01',  'SANTOS',     'MARIA',  NULL,           'Teacher', 'STEM Department',           'teacher123', 24, TRUE),
  ('FAC-ABM-01',   'DELA CRUZ',  'JUAN',   NULL,           'Teacher', 'ABM Department',            'teacher123', 22, TRUE),
  ('FAC-HUM-01',   'REYES',      'ANA',    NULL,           'Teacher', 'HUMSS Department',          'teacher123', 20, TRUE),
  ('FAC-ICT-01',   'MENDOZA',    'CARLO',  NULL,           'Teacher', 'ICT / Computer Systems Servicing', 'teacher123', 24, TRUE),
  ('FAC-CK-01',    'VILLANUEVA', 'ROSA',   NULL,           'Teacher', 'Cookery',                   'teacher123', 20, TRUE),
  ('FAC-EIM-01',   'GARCIA',     'PEDRO',  NULL,           'Teacher', 'Electrical Installation',   'teacher123', 22, TRUE),
  ('FAC-STEM-02',  'GARCIA',     'ANA',    'LOUISE',       'Teacher', 'STEM Department',           'teacher123', 24, TRUE)
ON CONFLICT (faculty_id) DO UPDATE SET
  last_name = EXCLUDED.last_name,
  first_name = EXCLUDED.first_name,
  middle_name = EXCLUDED.middle_name,
  role = EXCLUDED.role,
  department = EXCLUDED.department,
  max_load_units = EXCLUDED.max_load_units,
  is_active = TRUE;

-- Link professors → strands they teach
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id FROM faculty f, strands s WHERE f.faculty_id = 'FAC-STEM-01'  AND s.code = 'STEM'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id FROM faculty f, strands s WHERE f.faculty_id = 'FAC-STEM-02'  AND s.code = 'STEM'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id FROM faculty f, strands s WHERE f.faculty_id = 'FAC-ABM-01'   AND s.code = 'ABM'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id FROM faculty f, strands s WHERE f.faculty_id = 'FAC-HUM-01'   AND s.code = 'HUMSS'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id FROM faculty f, strands s WHERE f.faculty_id = 'FAC-ICT-01'   AND s.code = 'ICT'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id FROM faculty f, strands s WHERE f.faculty_id = 'FAC-CK-01'    AND s.code = 'COOKERY'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id FROM faculty f, strands s WHERE f.faculty_id = 'FAC-EIM-01'   AND s.code = 'EIM'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;

-- ── 3. SUBJECTS — Core (All Strands, strand_id = NULL) ───────
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units) VALUES
  ('CORE-01', 'Oral Communication',              'Oral Communication in Context',              NULL, 'Grade 11', 3, 0, 3),
  ('CORE-02', 'Reading and Writing',             'Reading and Writing Skills',                 NULL, 'Grade 11', 3, 0, 3),
  ('G11-C03', 'General Mathematics',             'General Mathematics',                        NULL, 'Grade 11', 3, 0, 3),
  ('GAS-01',  'Earth Science',                   'Earth and Life Science',                     NULL, 'Grade 11', 3, 0, 3),
  ('CORE-03', 'Media and Information Literacy',  'Media and Information Literacy',             NULL, 'Grade 12', 3, 0, 3),
  ('CORE-04', 'Philippine Politics and Governance', 'Philippine Politics and Governance',    NULL, 'Grade 12', 3, 0, 3),
  ('APPL-02', 'Practical Research 2',            'Practical Research 2',                     NULL, 'Grade 12', 3, 0, 3),
  ('PE-04',   'Physical Education 4',            'Physical Education and Health 4',          NULL, 'Grade 12', 2, 0, 2),
  ('WORK-01', 'Work Immersion',                  'Work Immersion',                             NULL, 'Grade 12', 3, 0, 3)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, description = EXCLUDED.description,
  grade_level = EXCLUDED.grade_level, units = EXCLUDED.units, is_active = TRUE;

-- ── 4. SUBJECTS — Academic Track ────────────────────────────
-- STEM
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('STEM-01',  'General Chemistry 1',   'General Chemistry 1',   'Grade 11', 3, 1, 4),
  ('G11-STEM-01','Pre-Calculus',        'Pre-Calculus',          'Grade 11', 4, 0, 4),
  ('G11-STEM-03','General Physics 1',   'General Physics 1',     'Grade 11', 3, 1, 4),
  ('STEM-G12', 'Pre-Calculus',          'Pre-Calculus',          'Grade 12', 4, 0, 4),
  ('STEM-02',  'General Physics 1',     'General Physics 1',     'Grade 12', 3, 1, 4),
  ('STEM-E01', 'Statistics and Probability','Statistics and Probability','Grade 12',3,0,3),
  ('STEM-03',  'General Chemistry 2',   'General Chemistry 2',   'Grade 12', 3, 1, 4)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'STEM'
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level, units = EXCLUDED.units, is_active = TRUE;

-- ABM
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('ABM-01',  'Business Mathematics',  'Business Mathematics',  'Grade 11', 3, 0, 3),
  ('G11-ABM-02','Fundamentals of ABM 1','Fundamentals of ABM 1','Grade 11', 3, 0, 3),
  ('ABM-G12', 'Business Finance',      'Business Finance',      'Grade 12', 3, 0, 3),
  ('ABM-02',  'Business Ethics',       'Business Ethics and Social Responsibility','Grade 12',3,0,3),
  ('ABM-03',  'FABM 2',                'Fundamentals of ABM 2', 'Grade 12', 3, 0, 3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'ABM'
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level, units = EXCLUDED.units, is_active = TRUE;

-- HUMSS
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-HUM-01','Creative Writing',      'Creative Writing',      'Grade 11', 3, 0, 3),
  ('HUMSS-01',  'Creative Writing',      'Creative Writing',      'Grade 12', 3, 0, 3),
  ('HUMSS-G12', 'Creative Writing',      'Creative Writing',      'Grade 12', 3, 0, 3),
  ('HUMSS-02',  'World Religions',       'Introduction to World Religions','Grade 12',3,0,3),
  ('HUMSS-03',  'Applied Social Sciences', 'Disciplines and Ideas in Applied Social Sciences','Grade 12',3,0,3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'HUMSS'
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level, units = EXCLUDED.units, is_active = TRUE;

-- GAS (Academic)
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-GAS-01','Humanities 1',          'Humanities 1',          'Grade 11', 3, 0, 3),
  ('GAS-G12-01','Humanities 2',          'Humanities 2',          'Grade 12', 3, 0, 3),
  ('GAS-G12-02','Social Science 2',      'Social Science 2',      'Grade 12', 3, 0, 3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'GAS'
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level, units = EXCLUDED.units, is_active = TRUE;

-- ── 5. SUBJECTS — TechPro Track ─────────────────────────────
-- ICT = CSS NC II (official SHS curriculum — see seed-shs-curriculum.sql)
-- Do NOT use old "Computer Programming" titles; they overwrite the CSS names.
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units, semester_code)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units, v.semester_code
FROM strands s,
(VALUES
  ('G11-ICT-01', 'CSS NC II – Install and Configure Computer Systems', 'CSS NC II – Install and Configure Computer Systems', 'Grade 11', 3, 1, 4, '1st'),
  ('G11-ICT-02', 'CSS NC II – Set Up Computer Networks', 'CSS NC II – Set Up Computer Networks', 'Grade 11', 3, 1, 4, '1st'),
  ('G11-ICT-03', 'CSS NC II – Install Computer Systems and Networks', 'CSS NC II – Install Computer Systems and Networks', 'Grade 11', 3, 1, 4, '2nd'),
  ('G11-ICT-04', 'CSS NC II – Maintain and Repair Computer Systems and Networks', 'CSS NC II – Maintain and Repair Computer Systems and Networks', 'Grade 11', 3, 1, 4, '2nd'),
  ('G12-ICT-01', 'CSS NC II – Diagnose and Troubleshoot Computer Systems', 'CSS NC II – Diagnose and Troubleshoot Computer Systems', 'Grade 12', 3, 1, 4, '1st'),
  ('G12-ICT-02', 'CSS NC II – Configure Network Services', 'CSS NC II – Configure Network Services', 'Grade 12', 3, 1, 4, '1st'),
  ('G12-ICT-03', 'Work Immersion', 'Work Immersion', 'Grade 12', 3, 0, 3, '2nd'),
  ('G12-ICT-04', 'Specialization Enhancement / Entrepreneurship Integration', 'Specialization Enhancement / Entrepreneurship Integration', 'Grade 12', 3, 0, 3, '2nd')
) AS v(code, name, description, grade_level, lec, lab, units, semester_code)
WHERE s.code = 'ICT'
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  strand_id = EXCLUDED.strand_id,
  grade_level = EXCLUDED.grade_level,
  lec_hours = EXCLUDED.lec_hours,
  lab_hours = EXCLUDED.lab_hours,
  units = EXCLUDED.units,
  semester_code = EXCLUDED.semester_code,
  is_active = TRUE;

-- Deactivate retired legacy ICT codes if they exist
UPDATE subjects SET is_active = FALSE
WHERE code IN ('ICT-G12', 'ICT-02', 'ICT-03', 'ICT-01');

-- Home Economics (HE)
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-HE-01','Household Services',      'Household Services',      'Grade 11', 3, 1, 4),
  ('G11-HE-02','Food and Beverage Services','Food and Beverage Services','Grade 11',3,1,4),
  ('HE-G12',  'Events Management',       'Events Management Services','Grade 12', 3, 1, 4),
  ('HE-02',   'Catering Services',       'Catering Services',       'Grade 12', 3, 1, 4)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'HE'
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level, units = EXCLUDED.units, is_active = TRUE;

-- Industrial Arts (INDARTS)
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-IA-01','Electrical Installation 1','Electrical Installation and Maintenance 1','Grade 11',3,1,4),
  ('G11-IA-02','Automotive Servicing 1',  'Automotive Servicing 1',  'Grade 11', 3, 1, 4),
  ('IA-G12',  'Electrical Installation 3','Electrical Installation and Maintenance 3','Grade 12',3,1,4),
  ('IA-02',   'Automotive Servicing 3',  'Automotive Servicing 3',  'Grade 12', 3, 1, 4)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'INDARTS'
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level, units = EXCLUDED.units, is_active = TRUE;

-- Permissions (safe to re-run)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
