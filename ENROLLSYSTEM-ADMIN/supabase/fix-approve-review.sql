-- ============================================================
-- FIX APPROVE / REJECT + High School Diploma + Student login
-- Run this ENTIRE file in Supabase SQL Editor, then restart server.
-- Fixes errors like:
--   column "password" of relation "students" does not exist
--   column "is_active" of relation "students" does not exist
--   Application not found or already processed
--   High School Diploma missing on review page
-- ============================================================

-- ── 1) Ensure students table has ALL columns used by approve + login ──
ALTER TABLE students ADD COLUMN IF NOT EXISTS middle_name TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS birthdate DATE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS password TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS gender TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS contact_number TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS admission_type TEXT DEFAULT 'new';
ALTER TABLE students ADD COLUMN IF NOT EXISTS admission_status TEXT DEFAULT 'enrolled';
ALTER TABLE students ADD COLUMN IF NOT EXISTS grade_level TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS strand_id UUID;
ALTER TABLE students ADD COLUMN IF NOT EXISTS section_id UUID;
ALTER TABLE students ADD COLUMN IF NOT EXISTS scholastic_status TEXT DEFAULT 'Regular';
ALTER TABLE students ADD COLUMN IF NOT EXISTS track TEXT DEFAULT 'Academic';
ALTER TABLE students ADD COLUMN IF NOT EXISTS voucher_qualified BOOLEAN DEFAULT FALSE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE students ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- ── 2) Admission applications — diploma + bank columns ──
ALTER TABLE admission_applications
  ADD COLUMN IF NOT EXISTS doc_high_school_diploma_path TEXT,
  ADD COLUMN IF NOT EXISTS bank_code TEXT,
  ADD COLUMN IF NOT EXISTS bank_reference TEXT,
  ADD COLUMN IF NOT EXISTS bank_sender_name TEXT,
  ADD COLUMN IF NOT EXISTS bank_proof_path TEXT;

UPDATE admission_applications
SET doc_high_school_diploma_path = COALESCE(
  doc_high_school_diploma_path,
  NULLIF(documents->>'high_school_diploma', '')
)
WHERE documents ? 'high_school_diploma';

-- ── 3) Drop old conflicting RPC signatures ──
DROP FUNCTION IF EXISTS get_admission_detail(UUID);
DROP FUNCTION IF EXISTS review_admission_application(UUID, TEXT, TEXT, TEXT);

-- ── 4) Student ID generator ──
CREATE OR REPLACE FUNCTION generate_student_id()
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  v_year TEXT;
  v_seq INT;
BEGIN
  v_year := TO_CHAR(NOW(), 'YYYY');
  SELECT COALESCE(MAX(
    NULLIF(SPLIT_PART(student_id, '-', 2), '')::INT
  ), 0) + 1
  INTO v_seq
  FROM students
  WHERE student_id LIKE v_year || '-%';

  RETURN v_year || '-' || LPAD(v_seq::TEXT, 5, '0') || '-SHS-0';
END;
$$;

-- ── 5) Submit — save high school diploma ──
CREATE OR REPLACE FUNCTION submit_admission_application(p_payload JSON)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_id UUID;
  v_app_number TEXT;
  v_count INT;
  v_docs JSONB;
  v_full_address TEXT;
BEGIN
  SELECT COUNT(*) + 1 INTO v_count FROM admission_applications;
  v_app_number := 'APP-' || TO_CHAR(NOW(), 'YYYY') || '-' || LPAD(v_count::TEXT, 5, '0');
  v_docs := COALESCE(p_payload->'documents', '{}'::json);

  v_full_address := NULLIF(CONCAT_WS(', ',
    NULLIF(TRIM(p_payload->>'houseNumber'), ''),
    NULLIF(TRIM(p_payload->>'street'), ''),
    NULLIF(TRIM(p_payload->>'barangay'), ''),
    NULLIF(TRIM(p_payload->>'city'), ''),
    NULLIF(TRIM(p_payload->>'province'), '')
  ), '');

  IF v_full_address IS NULL THEN
    v_full_address := NULLIF(TRIM(p_payload->>'address'), '');
  END IF;

  INSERT INTO admission_applications (
    application_number, last_name, first_name, middle_name, birthdate, gender,
    address, addr_house_number, addr_street, addr_barangay, addr_city, addr_province,
    contact_number, email, grade_level, strand_id, admission_type, previous_school,
    payment_mode, gcash_reference, gcash_sender_name, gcash_proof_path,
    payment_status, payment_amount,
    doc_form_138_path, doc_form_137_path, doc_good_moral_path,
    doc_birth_certificate_path, doc_high_school_diploma_path,
    documents, status
  )
  VALUES (
    v_app_number,
    UPPER(TRIM(p_payload->>'lastName')),
    UPPER(TRIM(p_payload->>'firstName')),
    NULLIF(UPPER(TRIM(p_payload->>'middleName')), ''),
    (p_payload->>'birthdate')::DATE,
    NULLIF(p_payload->>'gender', ''),
    v_full_address,
    NULLIF(TRIM(p_payload->>'houseNumber'), ''),
    NULLIF(TRIM(p_payload->>'street'), ''),
    NULLIF(TRIM(p_payload->>'barangay'), ''),
    NULLIF(TRIM(p_payload->>'city'), ''),
    NULLIF(TRIM(p_payload->>'province'), ''),
    p_payload->>'contactNumber',
    LOWER(TRIM(p_payload->>'email')),
    p_payload->>'gradeLevel',
    COALESCE(
      NULLIF(p_payload->>'strandId', '')::UUID,
      (SELECT id FROM strands WHERE code = UPPER(TRIM(p_payload->>'strandCode')) LIMIT 1)
    ),
    COALESCE(p_payload->>'admissionType', 'new'),
    NULLIF(TRIM(p_payload->>'previousSchool'), ''),
    p_payload->>'paymentMode',
    NULLIF(p_payload->>'gcashReference', ''),
    NULLIF(p_payload->>'gcashSenderName', ''),
    NULLIF(p_payload->>'gcashProofPath', ''),
    COALESCE(p_payload->>'paymentStatus', 'submitted'),
    NULLIF(p_payload->>'paymentAmount', '')::NUMERIC,
    NULLIF(COALESCE(p_payload->>'docForm138Path', v_docs->>'form_138'), ''),
    NULLIF(COALESCE(p_payload->>'docForm137Path', v_docs->>'form_137'), ''),
    NULLIF(COALESCE(p_payload->>'docGoodMoralPath', v_docs->>'good_moral'), ''),
    NULLIF(COALESCE(p_payload->>'docBirthCertificatePath', v_docs->>'birth_certificate'), ''),
    NULLIF(COALESCE(p_payload->>'docHighSchoolDiplomaPath', v_docs->>'high_school_diploma'), ''),
    jsonb_strip_nulls(jsonb_build_object(
      'form_138', NULLIF(COALESCE(p_payload->>'docForm138Path', v_docs->>'form_138'), ''),
      'form_137', NULLIF(COALESCE(p_payload->>'docForm137Path', v_docs->>'form_137'), ''),
      'good_moral', NULLIF(COALESCE(p_payload->>'docGoodMoralPath', v_docs->>'good_moral'), ''),
      'birth_certificate', NULLIF(COALESCE(p_payload->>'docBirthCertificatePath', v_docs->>'birth_certificate'), ''),
      'high_school_diploma', NULLIF(COALESCE(p_payload->>'docHighSchoolDiplomaPath', v_docs->>'high_school_diploma'), '')
    )),
    'pending'
  )
  RETURNING id INTO v_id;

  RETURN json_build_object(
    'success', TRUE,
    'applicationId', v_id,
    'applicationNumber', v_app_number
  );
END;
$$;

-- ── 6) Pending list — include diploma ──
CREATE OR REPLACE FUNCTION get_pending_admissions()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN (
    SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
    FROM (
      SELECT
        a.id,
        a.application_number AS "applicationNumber",
        a.last_name AS "lastName",
        a.first_name AS "firstName",
        a.middle_name AS "middleName",
        CONCAT(a.last_name, ', ', a.first_name, ' ', COALESCE(a.middle_name, '')) AS student,
        TO_CHAR(a.birthdate, 'YYYY-MM-DD') AS birthdate,
        a.gender,
        COALESCE(
          NULLIF(TRIM(a.address), ''),
          NULLIF(TRIM(CONCAT_WS(', ',
            NULLIF(a.addr_house_number, ''),
            NULLIF(a.addr_street, ''),
            NULLIF(a.addr_barangay, ''),
            NULLIF(a.addr_city, ''),
            NULLIF(a.addr_province, '')
          )), '')
        ) AS address,
        a.email,
        a.contact_number AS "contactNumber",
        str.code AS strand,
        a.grade_level AS grade,
        a.admission_type AS "admissionType",
        a.payment_mode AS "paymentMode",
        a.gcash_reference AS "gcashReference",
        a.gcash_sender_name AS "gcashSenderName",
        a.gcash_proof_path AS "gcashProofPath",
        a.payment_amount AS "paymentAmount",
        a.payment_status AS "paymentStatus",
        a.status,
        TO_CHAR(a.created_at, 'YYYY-MM-DD') AS date,
        a.doc_form_138_path AS "docForm138Path",
        a.doc_form_137_path AS "docForm137Path",
        a.doc_good_moral_path AS "docGoodMoralPath",
        a.doc_birth_certificate_path AS "docBirthCertificatePath",
        a.doc_high_school_diploma_path AS "docHighSchoolDiplomaPath",
        COALESCE(
          NULLIF(a.documents, '{}'::jsonb),
          jsonb_strip_nulls(jsonb_build_object(
            'form_138', a.doc_form_138_path,
            'form_137', a.doc_form_137_path,
            'good_moral', a.doc_good_moral_path,
            'birth_certificate', a.doc_birth_certificate_path,
            'high_school_diploma', a.doc_high_school_diploma_path
          ))
        ) AS documents
      FROM admission_applications a
      LEFT JOIN strands str ON str.id = a.strand_id
      WHERE a.status = 'pending'
      ORDER BY a.created_at DESC
    ) t
  );
END;
$$;

-- ── 7) Detail — UUID or APP number ──
CREATE OR REPLACE FUNCTION get_admission_detail(p_application_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_result JSON;
BEGIN
  SELECT row_to_json(t) INTO v_result
  FROM (
    SELECT
      a.id,
      a.application_number AS "applicationNumber",
      a.last_name AS "lastName",
      a.first_name AS "firstName",
      a.middle_name AS "middleName",
      CONCAT(a.last_name, ', ', a.first_name, ' ', COALESCE(a.middle_name, '')) AS student,
      TO_CHAR(a.birthdate, 'YYYY-MM-DD') AS birthdate,
      a.gender,
      COALESCE(
        NULLIF(TRIM(a.address), ''),
        NULLIF(TRIM(CONCAT_WS(', ',
          NULLIF(a.addr_house_number, ''),
          NULLIF(a.addr_street, ''),
          NULLIF(a.addr_barangay, ''),
          NULLIF(a.addr_city, ''),
          NULLIF(a.addr_province, '')
        )), '')
      ) AS address,
      a.email,
      a.contact_number AS "contactNumber",
      str.code AS "strandCode",
      a.grade_level AS "gradeLevel",
      a.admission_type AS "admissionType",
      a.payment_mode AS "paymentMode",
      a.gcash_reference AS "gcashReference",
      a.gcash_sender_name AS "gcashSenderName",
      a.gcash_proof_path AS "gcashProofPath",
      a.payment_amount AS "paymentAmount",
      a.payment_status AS "paymentStatus",
      a.status,
      TO_CHAR(a.created_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS "submittedAt",
      TO_CHAR(a.created_at, 'YYYY-MM-DD') AS date,
      a.student_id_generated AS "studentId",
      a.rejection_reason AS "rejectionReason",
      TO_CHAR(a.reviewed_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS "reviewedAt",
      a.doc_form_138_path AS "docForm138Path",
      a.doc_form_137_path AS "docForm137Path",
      a.doc_good_moral_path AS "docGoodMoralPath",
      a.doc_birth_certificate_path AS "docBirthCertificatePath",
      a.doc_high_school_diploma_path AS "docHighSchoolDiplomaPath",
      COALESCE(
        NULLIF(a.documents, '{}'::jsonb),
        jsonb_strip_nulls(jsonb_build_object(
          'form_138', a.doc_form_138_path,
          'form_137', a.doc_form_137_path,
          'good_moral', a.doc_good_moral_path,
          'birth_certificate', a.doc_birth_certificate_path,
          'high_school_diploma', a.doc_high_school_diploma_path
        ))
      ) AS documents
    FROM admission_applications a
    LEFT JOIN strands str ON str.id = a.strand_id
    WHERE a.id::TEXT = p_application_id
       OR a.application_number = p_application_id
    LIMIT 1
  ) t;

  RETURN v_result;
END;
$$;

-- ── 8) Review approve/reject ──
CREATE OR REPLACE FUNCTION review_admission_application(
  p_application_id TEXT,
  p_faculty_id TEXT,
  p_action TEXT,
  p_reason TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_faculty UUID;
  v_app admission_applications%ROWTYPE;
  v_new_status TEXT;
  v_student_id TEXT;
  v_temp_password TEXT;
  v_student_uuid UUID;
BEGIN
  SELECT id INTO v_faculty
  FROM faculty
  WHERE faculty_id = UPPER(TRIM(p_faculty_id))
  LIMIT 1;

  SELECT * INTO v_app
  FROM admission_applications
  WHERE id::TEXT = p_application_id
     OR application_number = p_application_id
  LIMIT 1;

  IF v_app.id IS NULL THEN
    RAISE EXCEPTION 'Application not found';
  END IF;

  IF v_app.status <> 'pending' THEN
    RAISE EXCEPTION 'Application already processed';
  END IF;

  v_new_status := CASE
    WHEN LOWER(p_action) = 'approve' THEN 'approved'
    WHEN LOWER(p_action) = 'reject' THEN 'rejected'
    ELSE NULL
  END;

  IF v_new_status IS NULL THEN
    RAISE EXCEPTION 'Invalid action';
  END IF;

  IF v_new_status = 'approved' THEN
    v_student_id := generate_student_id();
    v_temp_password := 'Shs' || LPAD(FLOOR(random() * 10000)::TEXT, 4, '0');

    INSERT INTO students (
      student_id,
      last_name,
      first_name,
      middle_name,
      birthdate,
      password,
      gender,
      address,
      contact_number,
      admission_type,
      admission_status,
      grade_level,
      strand_id,
      scholastic_status,
      track,
      is_active
    )
    VALUES (
      v_student_id,
      v_app.last_name,
      v_app.first_name,
      v_app.middle_name,
      v_app.birthdate,
      v_temp_password,
      v_app.gender,
      v_app.address,
      v_app.contact_number,
      COALESCE(v_app.admission_type, 'new'),
      'approved',
      v_app.grade_level,
      v_app.strand_id,
      'Regular',
      'Academic',
      TRUE
    )
    RETURNING id INTO v_student_uuid;

    BEGIN
      INSERT INTO notifications (student_id, title, message, type)
      VALUES (
        v_student_uuid,
        'Welcome to Enrollment Management System',
        'Your admission has been approved. Use your Student ID to sign in to the enrollment portal.',
        'announcement'
      );
    EXCEPTION WHEN OTHERS THEN
      NULL;
    END;

    UPDATE admission_applications
    SET
      status = 'approved',
      student_id_generated = v_student_id,
      temp_password = v_temp_password,
      reviewed_by = v_faculty,
      reviewed_at = NOW(),
      updated_at = NOW()
    WHERE id = v_app.id;

    RETURN json_build_object(
      'success', TRUE,
      'status', 'approved',
      'studentId', v_student_id,
      'tempPassword', v_temp_password,
      'email', v_app.email,
      'firstName', v_app.first_name,
      'applicationNumber', v_app.application_number
    );
  END IF;

  UPDATE admission_applications
  SET
    status = 'rejected',
    rejection_reason = p_reason,
    reviewed_by = v_faculty,
    reviewed_at = NOW(),
    updated_at = NOW()
  WHERE id = v_app.id;

  RETURN json_build_object(
    'success', TRUE,
    'status', 'rejected',
    'email', v_app.email,
    'firstName', v_app.first_name,
    'applicationNumber', v_app.application_number
  );
END;
$$;

GRANT EXECUTE ON FUNCTION generate_student_id TO anon, authenticated;
GRANT EXECUTE ON FUNCTION submit_admission_application TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_pending_admissions TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_admission_detail TO anon, authenticated;
GRANT EXECUTE ON FUNCTION review_admission_application TO anon, authenticated;

-- ── 9) Student login (Gmail credentials must work here) ──
-- See supabase/fix-student-login.sql — included below for one-run setup

UPDATE students SET is_active = TRUE WHERE is_active IS NULL;

UPDATE students s
SET password = a.temp_password
FROM admission_applications a
WHERE a.status = 'approved'
  AND UPPER(a.student_id_generated) = UPPER(s.student_id)
  AND a.temp_password IS NOT NULL
  AND (s.password IS NULL OR TRIM(s.password) = '');

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
BEGIN
  IF v_student_id = '' OR v_password = '' THEN
    RETURN NULL;
  END IF;

  SELECT json_build_object(
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
    'schoolYear', COALESCE(sy.label, '2026-2027'),
    'semester', COALESCE(sem.name, 'First Semester'),
    'voucherQualified', COALESCE(s.voucher_qualified, FALSE)
  )
  INTO result
  FROM students s
  LEFT JOIN strands st ON st.id = s.strand_id
  LEFT JOIN sections sec ON sec.id = s.section_id
  LEFT JOIN semesters sem ON sem.is_current = TRUE
  LEFT JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE UPPER(s.student_id) = v_student_id
    AND TRIM(s.password) = v_password
    AND EXTRACT(MONTH FROM s.birthdate) = p_birth_month
    AND EXTRACT(DAY FROM s.birthdate) = p_birth_day
    AND EXTRACT(YEAR FROM s.birthdate) = p_birth_year
    AND COALESCE(s.is_active, TRUE) = TRUE
  LIMIT 1;

  IF result IS NOT NULL THEN
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
    'schoolYear', '2026-2027',
    'semester', 'First Semester',
    'voucherQualified', FALSE
  )
  INTO result
  FROM admission_applications a
  LEFT JOIN strands st ON st.id = a.strand_id
  WHERE a.status = 'approved'
    AND UPPER(a.student_id_generated) = v_student_id
    AND TRIM(a.temp_password) = v_password
    AND EXTRACT(MONTH FROM a.birthdate) = p_birth_month
    AND EXTRACT(DAY FROM a.birthdate) = p_birth_day
    AND EXTRACT(YEAR FROM a.birthdate) = p_birth_year
  LIMIT 1;

  IF result IS NOT NULL THEN
    INSERT INTO students (
      student_id, last_name, first_name, middle_name, birthdate, password,
      gender, address, contact_number, admission_type, admission_status,
      grade_level, strand_id, scholastic_status, track, is_active
    )
    SELECT
      a.student_id_generated, a.last_name, a.first_name, a.middle_name,
      a.birthdate, a.temp_password, a.gender, a.address, a.contact_number,
      COALESCE(a.admission_type, 'new'), 'approved', a.grade_level, a.strand_id,
      'Regular', 'Academic', TRUE
    FROM admission_applications a
    WHERE a.status = 'approved'
      AND UPPER(a.student_id_generated) = v_student_id
    ON CONFLICT (student_id) DO UPDATE SET
      password = EXCLUDED.password,
      birthdate = EXCLUDED.birthdate,
      is_active = TRUE,
      updated_at = NOW();
  END IF;

  RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION authenticate_student TO anon, authenticated;
