-- SHS Curriculum seed — run in Supabase SQL Editor
-- Replaces old subjects with official SHS-Subjects.docx curriculum
-- Run AFTER schema.sql and faculty-strands-rooms.sql

-- Deactivate retired TechPro strands
UPDATE strands SET is_active = FALSE WHERE code IN ('CSS', 'HE', 'INDARTS', 'OTHER');

-- Upsert current strands
INSERT INTO strands (code, name, track) VALUES
  ('STEM',    'STEM - Science, Technology, Engineering, and Mathematics', 'Academic'),
  ('ABM',     'Accountancy, Business & Management', 'Academic'),
  ('HUMSS',   'Humanities & Social Sciences', 'Academic'),
  ('GAS',     'General Academic Strand', 'Academic'),
  ('ICT',     'Information and Communications Technology', 'TechPro'),
  ('COOKERY', 'Cookery', 'TechPro'),
  ('EIM',     'Electrical Installation and Maintenance', 'TechPro')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, track = EXCLUDED.track, is_active = TRUE;

-- Deactivate all existing subjects (preserves FK history)
UPDATE subjects SET is_active = FALSE;

-- Core + Applied (all strands)
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units) VALUES
  ('G11-C01', 'Oral Communication in Context', 'Oral Communication in Context', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C02', 'Komunikasyon at Pananaliksik sa Wika at Kulturang Pilipino', 'Komunikasyon at Pananaliksik sa Wika at Kulturang Pilipino', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C03', 'General Mathematics', 'General Mathematics', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C04', 'Earth and Life Science', 'Earth and Life Science', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C05', 'Personal Development', 'Personal Development', NULL, 'Grade 11', 3, 0, 3),
  ('G11-PE1', 'Physical Education and Health 1', 'Physical Education and Health 1', NULL, 'Grade 11', 2, 0, 2),
  ('G11-A01', 'Empowerment Technologies', 'Empowerment Technologies', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C06', 'Reading and Writing Skills', 'Reading and Writing Skills', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C07', 'Pagbasa at Pagsusuri ng Iba''t Ibang Teksto Tungo sa Pananaliksik', 'Pagbasa at Pagsusuri ng Iba''t Ibang Teksto Tungo sa Pananaliksik', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C08', 'Statistics and Probability', 'Statistics and Probability', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C09', 'Physical Science', 'Physical Science', NULL, 'Grade 11', 3, 0, 3),
  ('G11-C10', 'Understanding Culture, Society and Politics', 'Understanding Culture, Society and Politics', NULL, 'Grade 11', 3, 0, 3),
  ('G11-PE2', 'Physical Education and Health 2', 'Physical Education and Health 2', NULL, 'Grade 11', 2, 0, 2),
  ('G11-A02', 'Practical Research 1', 'Practical Research 1', NULL, 'Grade 11', 3, 0, 3),
  ('G12-C01', 'Introduction to the Philosophy of the Human Person', 'Introduction to the Philosophy of the Human Person', NULL, 'Grade 12', 3, 0, 3),
  ('G12-C02', 'Disaster Readiness and Risk Reduction', 'Disaster Readiness and Risk Reduction', NULL, 'Grade 12', 3, 0, 3),
  ('G12-PE3', 'Physical Education and Health 3', 'Physical Education and Health 3', NULL, 'Grade 12', 2, 0, 2),
  ('G12-A01', 'English for Academic and Professional Purposes', 'English for Academic and Professional Purposes', NULL, 'Grade 12', 3, 0, 3),
  ('G12-A02', 'Entrepreneurship', 'Entrepreneurship', NULL, 'Grade 12', 3, 0, 3),
  ('G12-A03', 'Filipino sa Piling Larang', 'Filipino sa Piling Larang', NULL, 'Grade 12', 3, 0, 3),
  ('G12-C03', 'Contemporary Philippine Arts from the Regions', 'Contemporary Philippine Arts from the Regions', NULL, 'Grade 12', 3, 0, 3),
  ('G12-PE4', 'Physical Education and Health 4', 'Physical Education and Health 4', NULL, 'Grade 12', 2, 0, 2),
  ('G12-A04', 'Inquiries, Investigations, and Immersion', 'Inquiries, Investigations, and Immersion', NULL, 'Grade 12', 3, 0, 3),
  ('G12-A05', 'Practical Research 2', 'Practical Research 2', NULL, 'Grade 12', 3, 0, 3),
  ('G12-A06', 'Work Immersion', 'Work Immersion', NULL, 'Grade 12', 3, 0, 3)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, description = EXCLUDED.description,
  strand_id = NULL, grade_level = EXCLUDED.grade_level,
  lec_hours = EXCLUDED.lec_hours, lab_hours = EXCLUDED.lab_hours,
  units = EXCLUDED.units, is_active = TRUE;

-- STEM specialized subjects
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-STEM-01', 'Pre-Calculus', 'Pre-Calculus', 'Grade 11', 4, 0, 4),
  ('G11-STEM-02', 'General Biology 1', 'General Biology 1', 'Grade 11', 3, 1, 4),
  ('G11-STEM-03', 'Earth Science', 'Earth Science', 'Grade 11', 3, 0, 3),
  ('G11-STEM-04', 'Basic Calculus', 'Basic Calculus', 'Grade 11', 4, 0, 4),
  ('G11-STEM-05', 'General Biology 2', 'General Biology 2', 'Grade 11', 3, 1, 4),
  ('G11-STEM-06', 'General Physics 1', 'General Physics 1', 'Grade 11', 3, 1, 4),
  ('G12-STEM-01', 'General Chemistry 1', 'General Chemistry 1', 'Grade 12', 3, 1, 4),
  ('G12-STEM-02', 'General Physics 2', 'General Physics 2', 'Grade 12', 3, 1, 4),
  ('G12-STEM-03', 'General Chemistry 2', 'General Chemistry 2', 'Grade 12', 3, 1, 4),
  ('G12-STEM-04', 'Research/Capstone', 'Research/Capstone', 'Grade 12', 3, 0, 3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'STEM'
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, description = EXCLUDED.description,
  strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level,
  lec_hours = EXCLUDED.lec_hours, lab_hours = EXCLUDED.lab_hours,
  units = EXCLUDED.units, is_active = TRUE;

-- ABM specialized subjects
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-ABM-01', 'Organization and Management', 'Organization and Management', 'Grade 11', 3, 0, 3),
  ('G11-ABM-02', 'Applied Economics', 'Applied Economics', 'Grade 11', 3, 0, 3),
  ('G11-ABM-03', 'Business Finance', 'Business Finance', 'Grade 11', 3, 0, 3),
  ('G11-ABM-04', 'Fundamentals of Accountancy, Business and Management 1', 'Fundamentals of Accountancy, Business and Management 1', 'Grade 11', 3, 0, 3),
  ('G12-ABM-01', 'Fundamentals of Accountancy, Business and Management 2', 'Fundamentals of Accountancy, Business and Management 2', 'Grade 12', 3, 0, 3),
  ('G12-ABM-02', 'Business Ethics and Social Responsibility', 'Business Ethics and Social Responsibility', 'Grade 12', 3, 0, 3),
  ('G12-ABM-03', 'Principles of Marketing', 'Principles of Marketing', 'Grade 12', 3, 0, 3),
  ('G12-ABM-04', 'Business Enterprise Simulation', 'Business Enterprise Simulation', 'Grade 12', 3, 0, 3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'ABM'
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, description = EXCLUDED.description,
  strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level,
  lec_hours = EXCLUDED.lec_hours, lab_hours = EXCLUDED.lab_hours,
  units = EXCLUDED.units, is_active = TRUE;

-- HUMSS specialized subjects
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-HUM-01', 'Disciplines and Ideas in the Social Sciences', 'Disciplines and Ideas in the Social Sciences', 'Grade 11', 3, 0, 3),
  ('G11-HUM-02', 'Creative Writing', 'Creative Writing', 'Grade 11', 3, 0, 3),
  ('G11-HUM-03', 'Philippine Politics and Governance', 'Philippine Politics and Governance', 'Grade 11', 3, 0, 3),
  ('G11-HUM-04', 'Disciplines and Ideas in the Applied Social Sciences', 'Disciplines and Ideas in the Applied Social Sciences', 'Grade 11', 3, 0, 3),
  ('G11-HUM-05', 'Creative Nonfiction', 'Creative Nonfiction', 'Grade 11', 3, 0, 3),
  ('G11-HUM-06', 'Community Engagement, Solidarity and Citizenship', 'Community Engagement, Solidarity and Citizenship', 'Grade 11', 3, 0, 3),
  ('G12-HUM-01', 'Trends, Networks and Critical Thinking in the 21st Century', 'Trends, Networks and Critical Thinking in the 21st Century', 'Grade 12', 3, 0, 3),
  ('G12-HUM-02', 'Introduction to World Religions and Belief Systems', 'Introduction to World Religions and Belief Systems', 'Grade 12', 3, 0, 3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'HUMSS'
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, description = EXCLUDED.description,
  strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level,
  lec_hours = EXCLUDED.lec_hours, lab_hours = EXCLUDED.lab_hours,
  units = EXCLUDED.units, is_active = TRUE;

-- ICT specialized subjects
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-ICT-01', 'CSS NC II – Install and Configure Computer Systems', 'CSS NC II – Install and Configure Computer Systems', 'Grade 11', 3, 1, 4),
  ('G11-ICT-02', 'CSS NC II – Set Up Computer Networks', 'CSS NC II – Set Up Computer Networks', 'Grade 11', 3, 1, 4),
  ('G11-ICT-03', 'CSS NC II – Install Computer Systems and Networks', 'CSS NC II – Install Computer Systems and Networks', 'Grade 11', 3, 1, 4),
  ('G11-ICT-04', 'CSS NC II – Maintain and Repair Computer Systems and Networks', 'CSS NC II – Maintain and Repair Computer Systems and Networks', 'Grade 11', 3, 1, 4),
  ('G12-ICT-01', 'CSS NC II – Diagnose and Troubleshoot Computer Systems', 'CSS NC II – Diagnose and Troubleshoot Computer Systems', 'Grade 12', 3, 1, 4),
  ('G12-ICT-02', 'CSS NC II – Configure Network Services', 'CSS NC II – Configure Network Services', 'Grade 12', 3, 1, 4),
  ('G12-ICT-03', 'Work Immersion', 'Work Immersion', 'Grade 12', 3, 0, 3),
  ('G12-ICT-04', 'Specialization Enhancement / Entrepreneurship Integration', 'Specialization Enhancement / Entrepreneurship Integration', 'Grade 12', 3, 0, 3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'ICT'
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, description = EXCLUDED.description,
  strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level,
  lec_hours = EXCLUDED.lec_hours, lab_hours = EXCLUDED.lab_hours,
  units = EXCLUDED.units, is_active = TRUE;

-- COOKERY specialized subjects
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-CK-01', 'Use Kitchen Tools, Equipment, and Paraphernalia', 'Use Kitchen Tools, Equipment, and Paraphernalia', 'Grade 11', 3, 1, 4),
  ('G11-CK-02', 'Perform Mensuration and Calculation', 'Perform Mensuration and Calculation', 'Grade 11', 3, 1, 4),
  ('G11-CK-03', 'Interpret Kitchen Layout', 'Interpret Kitchen Layout', 'Grade 11', 3, 1, 4),
  ('G11-CK-04', 'Practice Occupational Health and Safety Procedures', 'Practice Occupational Health and Safety Procedures', 'Grade 11', 3, 1, 4),
  ('G11-CK-05', 'Clean and Maintain Kitchen Tools, Equipment, and Premises', 'Clean and Maintain Kitchen Tools, Equipment, and Premises', 'Grade 11', 3, 1, 4),
  ('G11-CK-06', 'Prepare Appetizers', 'Prepare Appetizers', 'Grade 11', 3, 1, 4),
  ('G11-CK-07', 'Prepare Salads and Dressings', 'Prepare Salads and Dressings', 'Grade 11', 3, 1, 4),
  ('G11-CK-08', 'Prepare Sandwiches', 'Prepare Sandwiches', 'Grade 11', 3, 1, 4),
  ('G11-CK-09', 'Prepare Egg Dishes', 'Prepare Egg Dishes', 'Grade 11', 3, 1, 4),
  ('G11-CK-10', 'Prepare Vegetables', 'Prepare Vegetables', 'Grade 11', 3, 1, 4),
  ('G11-CK-11', 'Prepare Seafood Dishes', 'Prepare Seafood Dishes', 'Grade 11', 3, 1, 4),
  ('G12-CK-01', 'Prepare Stocks, Sauces and Soups', 'Prepare Stocks, Sauces and Soups', 'Grade 12', 3, 1, 4),
  ('G12-CK-02', 'Prepare Poultry and Game Dishes', 'Prepare Poultry and Game Dishes', 'Grade 12', 3, 1, 4),
  ('G12-CK-03', 'Prepare Meat Dishes', 'Prepare Meat Dishes', 'Grade 12', 3, 1, 4),
  ('G12-CK-04', 'Prepare Desserts', 'Prepare Desserts', 'Grade 12', 3, 1, 4),
  ('G12-CK-05', 'Prepare Cakes', 'Prepare Cakes', 'Grade 12', 3, 1, 4),
  ('G12-CK-06', 'Prepare Pastries', 'Prepare Pastries', 'Grade 12', 3, 1, 4),
  ('G12-CK-07', 'Package Prepared Food', 'Package Prepared Food', 'Grade 12', 3, 1, 4),
  ('G12-CK-08', 'Work Immersion', 'Work Immersion', 'Grade 12', 3, 0, 3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'COOKERY'
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, description = EXCLUDED.description,
  strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level,
  lec_hours = EXCLUDED.lec_hours, lab_hours = EXCLUDED.lab_hours,
  units = EXCLUDED.units, is_active = TRUE;

-- EIM specialized subjects
INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT v.code, v.name, v.description, s.id, v.grade_level, v.lec, v.lab, v.units
FROM strands s,
(VALUES
  ('G11-EIM-01', 'Prepare Electrical Materials and Tools', 'Prepare Electrical Materials and Tools', 'Grade 11', 3, 1, 4),
  ('G11-EIM-02', 'Interpret Technical Drawings and Plans', 'Interpret Technical Drawings and Plans', 'Grade 11', 3, 1, 4),
  ('G11-EIM-03', 'Perform Mensuration and Calculation', 'Perform Mensuration and Calculation', 'Grade 11', 3, 1, 4),
  ('G11-EIM-04', 'Practice Occupational Safety and Health Procedures', 'Practice Occupational Safety and Health Procedures', 'Grade 11', 3, 1, 4),
  ('G11-EIM-05', 'Install Electrical Lighting System', 'Install Electrical Lighting System', 'Grade 11', 3, 1, 4),
  ('G11-EIM-06', 'Install Wiring Devices', 'Install Wiring Devices', 'Grade 11', 3, 1, 4),
  ('G11-EIM-07', 'Install Conduit, Tubing and Fittings', 'Install Conduit, Tubing and Fittings', 'Grade 11', 3, 1, 4),
  ('G12-EIM-01', 'Install Electrical Protection System', 'Install Electrical Protection System', 'Grade 12', 3, 1, 4),
  ('G12-EIM-02', 'Install Electrical Control System', 'Install Electrical Control System', 'Grade 12', 3, 1, 4),
  ('G12-EIM-03', 'Maintain and Repair Electrical Systems', 'Maintain and Repair Electrical Systems', 'Grade 12', 3, 1, 4),
  ('G12-EIM-04', 'Test and Commission Electrical Installation', 'Test and Commission Electrical Installation', 'Grade 12', 3, 1, 4),
  ('G12-EIM-05', 'Work Immersion', 'Work Immersion', 'Grade 12', 3, 0, 3)
) AS v(code, name, description, grade_level, lec, lab, units)
WHERE s.code = 'EIM'
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name, description = EXCLUDED.description,
  strand_id = EXCLUDED.strand_id, grade_level = EXCLUDED.grade_level,
  lec_hours = EXCLUDED.lec_hours, lab_hours = EXCLUDED.lab_hours,
  units = EXCLUDED.units, is_active = TRUE;

-- Active subject count: 90