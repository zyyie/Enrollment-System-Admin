-- Fix student login after admission approval
-- Run this in Supabase SQL Editor if Gmail credentials do not work on login
-- Safe to re-run anytime

ALTER TABLE students ADD COLUMN IF NOT EXISTS password TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS birthdate DATE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS grade_level TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS strand_id UUID;
ALTER TABLE students ADD COLUMN IF NOT EXISTS track TEXT DEFAULT 'Academic';
ALTER TABLE students ADD COLUMN IF NOT EXISTS admission_status TEXT DEFAULT 'enrolled';
ALTER TABLE students ADD COLUMN IF NOT EXISTS scholastic_status TEXT DEFAULT 'Regular';
ALTER TABLE students ADD COLUMN IF NOT EXISTS account_status TEXT DEFAULT 'active';

UPDATE students SET is_active = TRUE WHERE is_active IS NULL;
UPDATE students SET account_status = 'active' WHERE account_status IS NULL;

-- Sync password from approved admissions (matches approval email)
UPDATE students s
SET
  password = a.temp_password,
  birthdate = COALESCE(s.birthdate, a.birthdate),
  is_active = TRUE,
  account_status = 'active',
  updated_at = NOW()
FROM admission_applications a
WHERE a.status = 'approved'
  AND UPPER(a.student_id_generated) = UPPER(s.student_id)
  AND a.temp_password IS NOT NULL
  AND (
    s.password IS NULL OR TRIM(s.password) = ''
    OR TRIM(s.password) <> TRIM(a.temp_password)
  );

CREATE OR REPLACE FUNCTION authenticate_student(
  p_student_id TEXT,
  p_birth_month INT,
  p_birth_day INT,
  p_birth_year INT,
  p_password TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
  v_password TEXT := TRIM(p_password);
  v_student_id TEXT := UPPER(TRIM(p_student_id));
  v_account_status TEXT;
BEGIN
  IF v_student_id = '' OR v_password = '' THEN
    RETURN NULL;
  END IF;

  SELECT
    COALESCE(s.account_status, 'active'),
    json_build_object(
      'id', s.student_id,
      'supabaseId', s.id,
      'lastName', s.last_name,
      'firstName', s.first_name,
      'middleName', COALESCE(s.middle_name, ''),
      'birthMonth', EXTRACT(MONTH FROM s.birthdate)::TEXT,
      'birthDay', EXTRACT(DAY FROM s.birthdate)::TEXT,
      'birthYear', EXTRACT(YEAR FROM s.birthdate)::TEXT,
      'gradeLevel', s.grade_level,
      'strand', COALESCE(st.code, 'GAS'),
      'strandFull', COALESCE(st.name, st.code, 'GAS'),
      'section', COALESCE(sec.name, ''),
      'track', COALESCE(s.track, 'Academic'),
      'admissionStatus', COALESCE(s.admission_status, 'approved'),
      'scholasticStatus', COALESCE(s.scholastic_status, 'Regular'),
      'accountStatus', COALESCE(s.account_status, 'active'),
      'progressionStatus', COALESCE(s.progression_status, 'in_progress'),
      'grade11Completed', COALESCE(s.grade11_completed, FALSE),
      'schoolYear', COALESCE(sy.label, '2026-2027'),
      'semester', COALESCE(sem.name, 'First Semester'),
      'semesterCode', COALESCE(sem.code, '1st'),
      'enrollmentOpen', COALESCE(sem.enrollment_open, FALSE),
      'voucherQualified', COALESCE(s.voucher_qualified, FALSE)
    )
  INTO v_account_status, result
  FROM students s
  LEFT JOIN strands st ON st.id = s.strand_id
  LEFT JOIN sections sec ON sec.id = s.section_id
  LEFT JOIN semesters sem ON sem.is_current = TRUE
  LEFT JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE UPPER(s.student_id) = v_student_id
    AND TRIM(s.password) = v_password
    AND s.birthdate IS NOT NULL
    AND EXTRACT(MONTH FROM s.birthdate)::INT = p_birth_month
    AND EXTRACT(DAY FROM s.birthdate)::INT = p_birth_day
    AND EXTRACT(YEAR FROM s.birthdate)::INT = p_birth_year
    AND COALESCE(s.is_active, TRUE) = TRUE
  LIMIT 1;

  IF result IS NOT NULL THEN
    IF v_account_status = 'frozen' THEN
      RETURN json_build_object(
        'error', 'ACCOUNT_FROZEN',
        'message', 'Your account has been frozen due to non-enrollment during the official registration period. Please contact the registrar''s office.'
      );
    END IF;
    IF v_account_status = 'inactive' THEN
      RETURN json_build_object(
        'error', 'ACCOUNT_INACTIVE',
        'message', 'Your account is inactive. Please contact the registrar''s office.'
      );
    END IF;
    RETURN result;
  END IF;

  SELECT json_build_object(
    'id', a.student_id_generated,
    'supabaseId', NULL,
    'lastName', a.last_name,
    'firstName', a.first_name,
    'middleName', COALESCE(a.middle_name, ''),
    'birthMonth', EXTRACT(MONTH FROM a.birthdate)::TEXT,
    'birthDay', EXTRACT(DAY FROM a.birthdate)::TEXT,
    'birthYear', EXTRACT(YEAR FROM a.birthdate)::TEXT,
    'gradeLevel', a.grade_level,
    'strand', COALESCE(st.code, 'GAS'),
    'strandFull', COALESCE(st.name, st.code, 'GAS'),
    'section', '',
    'track', 'Academic',
    'admissionStatus', 'approved',
    'scholasticStatus', 'Regular',
    'accountStatus', 'active',
    'progressionStatus', 'in_progress',
    'grade11Completed', FALSE,
    'schoolYear', '2026-2027',
    'semester', 'First Semester',
    'semesterCode', '1st',
    'enrollmentOpen', FALSE,
    'voucherQualified', FALSE
  )
  INTO result
  FROM admission_applications a
  LEFT JOIN strands st ON st.id = a.strand_id
  WHERE a.status = 'approved'
    AND UPPER(a.student_id_generated) = v_student_id
    AND TRIM(a.temp_password) = v_password
    AND a.birthdate IS NOT NULL
    AND EXTRACT(MONTH FROM a.birthdate)::INT = p_birth_month
    AND EXTRACT(DAY FROM a.birthdate)::INT = p_birth_day
    AND EXTRACT(YEAR FROM a.birthdate)::INT = p_birth_year
  LIMIT 1;

  IF result IS NOT NULL THEN
    INSERT INTO students (
      student_id, last_name, first_name, middle_name, birthdate, password,
      gender, address, contact_number, admission_type, admission_status,
      grade_level, strand_id, scholastic_status, track, is_active, account_status
    )
    SELECT
      a.student_id_generated, a.last_name, a.first_name, a.middle_name,
      a.birthdate, a.temp_password, a.gender, a.address, a.contact_number,
      COALESCE(a.admission_type, 'new'), 'approved', a.grade_level, a.strand_id,
      'Regular', 'Academic', TRUE, 'active'
    FROM admission_applications a
    WHERE a.status = 'approved'
      AND UPPER(a.student_id_generated) = v_student_id
    ON CONFLICT (student_id) DO UPDATE SET
      password = EXCLUDED.password,
      birthdate = EXCLUDED.birthdate,
      is_active = TRUE,
      account_status = 'active',
      updated_at = NOW();
  END IF;

  RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION authenticate_student TO anon, authenticated, service_role;
