-- Full SHS faculty roster (107 teachers) — max 3 subjects per semester each
-- Run in Supabase SQL Editor AFTER faculty-strands-rooms.sql
-- Safe to re-run (ON CONFLICT updates).

INSERT INTO faculty (faculty_id, last_name, first_name, role, department, password, max_load_units, is_active) VALUES
  ('FAC-STEM-01', 'SANTOS', 'MARIA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-02', 'REYES', 'JOSHUA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-03', 'CRUZ', 'ANGELA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-04', 'AQUINO', 'DANIEL', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-05', 'GARCIA', 'PATRICIA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-06', 'BAUTISTA', 'KEVIN', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-07', 'LIM', 'SOFIA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-08', 'VILLANUEVA', 'MARK', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-09', 'NAVARRO', 'RACHEL', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-10', 'RAMOS', 'VICTOR', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-11', 'MENDOZA', 'LAURA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-12', 'FLORES', 'HENRY', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-13', 'CASTILLO', 'NINA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-14', 'REYES', 'OWEN', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-15', 'REYES', 'CLARA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-16', 'MENDOZA', 'PAULA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-17', 'VILLANUEVA', 'ERIC', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-18', 'RAMOS', 'GRACE', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-19', 'FLORES', 'ADRIAN', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-20', 'BAUTISTA', 'LARA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-21', 'SANTOS', 'NOAH', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-STEM-22', 'REYES', 'MIA', 'Teacher', 'STEM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-01', 'VILLANUEVA', 'ANDREA', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-02', 'SY', 'MIGUEL', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-03', 'ONG', 'CARLA', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-04', 'FLORES', 'RAMON', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-05', 'TAN', 'GRACE', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-06', 'MERCADO', 'PAOLO', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-07', 'CHUA', 'LIZA', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-08', 'REYES', 'MONICA', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-09', 'SANTOS', 'JEROME', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-10', 'NAVARRO', 'BEA', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-11', 'LIM', 'CARLOS', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-12', 'CRUZ', 'DIANA', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-13', 'GARCIA', 'FELIX', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-14', 'RAMOS', 'NORA', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-15', 'BAUTISTA', 'IVAN', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-16', 'SY', 'CHLOE', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-17', 'ONG', 'MARCO', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-18', 'FLORES', 'LEAH', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-19', 'MERCADO', 'RYAN', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-ABM-20', 'CHUA', 'ELLA', 'Teacher', 'ABM Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-01', 'FERNANDEZ', 'JESSA', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-02', 'DELA CRUZ', 'LUIS', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-03', 'BAUTISTA', 'KAREN', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-04', 'VILLANUEVA', 'ETHAN', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-05', 'RAMOS', 'NICOLE', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-06', 'SANTOS', 'ERIC', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-07', 'REYES', 'LAURA', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-08', 'FLORES', 'MIGUEL', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-09', 'CRUZ', 'ANNA', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-10', 'TAN', 'GABRIEL', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-11', 'MERCADO', 'SOFIA', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-12', 'GARCIA', 'RINA', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-13', 'SY', 'PAOLO', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-14', 'DIZON', 'CLARA', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-15', 'FERNANDEZ', 'MARA', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-16', 'CRUZ', 'JONAS', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-17', 'SANTOS', 'LEAH', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-HUMSS-18', 'BAUTISTA', 'NICO', 'Teacher', 'HUMSS Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-01', 'REYES', 'ANA', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-02', 'CRUZ', 'BEN', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-03', 'SANTOS', 'CLARA', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-04', 'RAMOS', 'DIEGO', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-05', 'GARCIA', 'ELLA', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-06', 'NAVARRO', 'FELIX', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-07', 'DELA CRUZ', 'GRACE', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-08', 'LIM', 'HANNAH', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-09', 'SANTOS', 'IRENE', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-10', 'REYES', 'MARCO', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-11', 'CRUZ', 'NINA', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-12', 'TAN', 'OSCAR', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-13', 'GARCIA', 'PAULA', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-14', 'FLORES', 'RICO', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-15', 'RAMOS', 'MIA', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-COOKERY-16', 'SANTOS', 'LEO', 'Teacher', 'Cookery Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-01', 'GARCIA', 'RAMON', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-02', 'SANTOS', 'LEO', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-03', 'REYES', 'MAY', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-04', 'TORRES', 'CARLO', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-05', 'BAUTISTA', 'NINA', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-06', 'FLORES', 'OMAR', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-07', 'CRUZ', 'PAOLO', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-08', 'SANTOS', 'RHEA', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-09', 'LIM', 'VICTOR', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-10', 'REYES', 'DAISY', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-11', 'DIZON', 'MARCO', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-12', 'GARCIA', 'LARA', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-13', 'RAMOS', 'NOEL', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-14', 'SANTOS', 'AIDEN', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-EIM-15', 'CRUZ', 'MIKA', 'Teacher', 'EIM Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-01', 'LOPEZ', 'ADRIAN', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-02', 'DIZON', 'BRIAN', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-03', 'TAN', 'VINCE', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-04', 'CRUZ', 'ELLA', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-05', 'REYES', 'PAOLO', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-06', 'LIM', 'GRACE', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-07', 'SANTOS', 'CARLO', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-08', 'NAVARRO', 'MIA', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-09', 'GARCIA', 'JASON', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-10', 'FLORES', 'NINA', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-11', 'CRUZ', 'RYAN', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-12', 'SANTOS', 'TRISHA', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-13', 'DELA CRUZ', 'KEVIN', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-14', 'RAMOS', 'AVA', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-15', 'DIZON', 'LEO', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE),
  ('FAC-ICT-16', 'LOPEZ', 'MARA', 'Teacher', 'ICT Department', 'teacher123', 3, TRUE)
ON CONFLICT (faculty_id) DO UPDATE SET
  last_name = EXCLUDED.last_name,
  first_name = EXCLUDED.first_name,
  department = EXCLUDED.department,
  max_load_units = 3,
  is_active = TRUE;

-- Link STEM teachers
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id
FROM faculty f
JOIN strands s ON s.code = 'STEM'
WHERE f.faculty_id LIKE 'FAC-STEM-%'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;

-- Link ABM teachers
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id
FROM faculty f
JOIN strands s ON s.code = 'ABM'
WHERE f.faculty_id LIKE 'FAC-ABM-%'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;

-- Link HUMSS teachers
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id
FROM faculty f
JOIN strands s ON s.code = 'HUMSS'
WHERE f.faculty_id LIKE 'FAC-HUMSS-%'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;

-- Link COOKERY teachers
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id
FROM faculty f
JOIN strands s ON s.code = 'COOKERY'
WHERE f.faculty_id LIKE 'FAC-COOKERY-%'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;

-- Link EIM teachers
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id
FROM faculty f
JOIN strands s ON s.code = 'EIM'
WHERE f.faculty_id LIKE 'FAC-EIM-%'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;

-- Link ICT teachers
INSERT INTO faculty_strands (faculty_id, strand_id)
SELECT f.id, s.id
FROM faculty f
JOIN strands s ON s.code = 'ICT'
WHERE f.faculty_id LIKE 'FAC-ICT-%'
ON CONFLICT (faculty_id, strand_id) DO NOTHING;

-- Summary counts per strand
SELECT 'STEM' AS strand, COUNT(*) AS teachers
FROM faculty f
JOIN faculty_strands fs ON fs.faculty_id = f.id
JOIN strands s ON s.id = fs.strand_id
WHERE s.code = 'STEM' AND f.faculty_id LIKE 'FAC-STEM-%' AND f.is_active = TRUE;

SELECT 'ABM' AS strand, COUNT(*) AS teachers
FROM faculty f
JOIN faculty_strands fs ON fs.faculty_id = f.id
JOIN strands s ON s.id = fs.strand_id
WHERE s.code = 'ABM' AND f.faculty_id LIKE 'FAC-ABM-%' AND f.is_active = TRUE;

SELECT 'HUMSS' AS strand, COUNT(*) AS teachers
FROM faculty f
JOIN faculty_strands fs ON fs.faculty_id = f.id
JOIN strands s ON s.id = fs.strand_id
WHERE s.code = 'HUMSS' AND f.faculty_id LIKE 'FAC-HUMSS-%' AND f.is_active = TRUE;

SELECT 'COOKERY' AS strand, COUNT(*) AS teachers
FROM faculty f
JOIN faculty_strands fs ON fs.faculty_id = f.id
JOIN strands s ON s.id = fs.strand_id
WHERE s.code = 'COOKERY' AND f.faculty_id LIKE 'FAC-COOKERY-%' AND f.is_active = TRUE;

SELECT 'EIM' AS strand, COUNT(*) AS teachers
FROM faculty f
JOIN faculty_strands fs ON fs.faculty_id = f.id
JOIN strands s ON s.id = fs.strand_id
WHERE s.code = 'EIM' AND f.faculty_id LIKE 'FAC-EIM-%' AND f.is_active = TRUE;

SELECT 'ICT' AS strand, COUNT(*) AS teachers
FROM faculty f
JOIN faculty_strands fs ON fs.faculty_id = f.id
JOIN strands s ON s.id = fs.strand_id
WHERE s.code = 'ICT' AND f.faculty_id LIKE 'FAC-ICT-%' AND f.is_active = TRUE;

-- Optional: deactivate old sample teachers replaced by this roster
UPDATE faculty SET is_active = FALSE
WHERE faculty_id IN (
  'FAC-CK-01', 'FAC-CSS-01', 'FAC-GAS-01', 'FAC-HE-01', 'FAC-HUM-01', 'FAC-IA-01'
);
