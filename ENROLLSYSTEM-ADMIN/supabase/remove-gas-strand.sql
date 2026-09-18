-- Remove deprecated strands (GAS, CSS, HE, INDARTS, OTHER) from EMS
-- ICT = CSS NC II (Computer Systems Servicing) — CSS is NOT a separate strand
-- Run once in Supabase SQL Editor

UPDATE strands
SET is_active = FALSE
WHERE UPPER(code) IN ('GAS', 'CSS', 'HE', 'INDARTS', 'OTHER');

-- Remove deprecated strand links from professors
DELETE FROM faculty_strands
WHERE strand_id IN (
 SELECT id FROM strands WHERE UPPER(code) IN ('GAS', 'CSS', 'HE', 'INDARTS', 'OTHER')
);

-- Deactivate professors tied to deprecated strands
UPDATE faculty
SET is_active = FALSE, updated_at = NOW()
WHERE role = 'Teacher'
 AND (
 UPPER(faculty_id) LIKE '%-GAS-%'
 OR UPPER(faculty_id) LIKE '%-CSS-%'
 OR UPPER(faculty_id) LIKE '%-HE-%'
 OR UPPER(faculty_id) LIKE '%-INDARTS-%'
 OR UPPER(COALESCE(department, '')) LIKE 'GAS %'
 OR UPPER(COALESCE(department, '')) LIKE 'CSS %'
 OR UPPER(COALESCE(department, '')) LIKE 'HE %'
 OR UPPER(COALESCE(department, '')) LIKE 'INDARTS %'
 OR UPPER(COALESCE(department, '')) = 'COMPUTER SYSTEMS SERVICING'
 );

-- Deactivate deprecated strand subjects (CSS, GAS, HE, INDARTS)
UPDATE subjects
SET is_active = FALSE
WHERE strand_id IN (
 SELECT id FROM strands WHERE UPPER(code) IN ('GAS', 'CSS', 'HE', 'INDARTS', 'OTHER')
);

UPDATE subjects
SET is_active = FALSE
WHERE UPPER(code) LIKE 'G11-CSS-%' OR UPPER(code) LIKE 'G12-CSS-%' OR UPPER(code) LIKE 'CSS-%'
 OR UPPER(code) LIKE 'G11-GAS-%' OR UPPER(code) LIKE 'G12-GAS-%' OR UPPER(code) LIKE 'GAS-%'
 OR UPPER(code) LIKE 'G11-HE-%' OR UPPER(code) LIKE 'G12-HE-%' OR UPPER(code) LIKE 'HE-%'
 OR UPPER(code) LIKE 'G11-IA-%' OR UPPER(code) LIKE 'G12-IA-%' OR UPPER(code) LIKE 'IA-%'
 OR UPPER(code) LIKE 'INDARTS-%';

-- Verify active strands (expect STEM, ABM, HUMSS, ICT, COOKERY, EIM)
SELECT code, name, track, is_active FROM strands ORDER BY code;

-- Verify deprecated faculty deactivated (FAC-ICT-01 should stay active)
SELECT faculty_id, first_name, last_name, department, is_active
FROM faculty
WHERE role = 'Teacher'
ORDER BY faculty_id;
