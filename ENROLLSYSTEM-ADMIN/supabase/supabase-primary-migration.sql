-- ============================================================
-- Supabase-primary migration
-- Run this ONCE in Supabase SQL Editor so enrollments save to Supabase only.
-- Includes: high school diploma, bank payment, updated RPCs
-- ============================================================

-- Remove old UUID-only RPC signatures (they break APP-2026-xxxxx lookups)
DROP FUNCTION IF EXISTS get_admission_detail(UUID);
DROP FUNCTION IF EXISTS review_admission_application(UUID, TEXT, TEXT, TEXT);

-- Students table must have all columns for approve + login
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

ALTER TABLE admission_applications
  ADD COLUMN IF NOT EXISTS doc_high_school_diploma_path TEXT,
  ADD COLUMN IF NOT EXISTS bank_code TEXT,
  ADD COLUMN IF NOT EXISTS bank_reference TEXT,
  ADD COLUMN IF NOT EXISTS bank_sender_name TEXT,
  ADD COLUMN IF NOT EXISTS bank_proof_path TEXT;

ALTER TABLE admission_applications
  DROP CONSTRAINT IF EXISTS admission_applications_payment_mode_check;

ALTER TABLE admission_applications
  ADD CONSTRAINT admission_applications_payment_mode_check
  CHECK (payment_mode IN ('gcash', 'cashier', 'bank'));

UPDATE admission_applications
SET doc_high_school_diploma_path = COALESCE(
  doc_high_school_diploma_path,
  documents->>'high_school_diploma'
)
WHERE documents ? 'high_school_diploma';

-- ============================================================
-- SUBMIT
-- ============================================================

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
    payment_mode,
    gcash_reference, gcash_sender_name, gcash_proof_path,
    bank_code, bank_reference, bank_sender_name, bank_proof_path,
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
    NULLIF(p_payload->>'bankCode', ''),
    NULLIF(p_payload->>'bankReference', ''),
    NULLIF(p_payload->>'bankSenderName', ''),
    NULLIF(p_payload->>'bankProofPath', ''),
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

-- ============================================================
-- PENDING LIST
-- ============================================================

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
        a.previous_school AS "previousSchool",
        a.payment_mode AS "paymentMode",
        a.gcash_reference AS "gcashReference",
        a.gcash_sender_name AS "gcashSenderName",
        a.gcash_proof_path AS "gcashProofPath",
        a.bank_code AS "bankCode",
        a.bank_reference AS "bankReference",
        a.bank_sender_name AS "bankSenderName",
        a.bank_proof_path AS "bankProofPath",
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

-- ============================================================
-- DETAIL
-- ============================================================

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
      a.previous_school AS "previousSchool",
      a.payment_mode AS "paymentMode",
      a.gcash_reference AS "gcashReference",
      a.gcash_sender_name AS "gcashSenderName",
      a.gcash_proof_path AS "gcashProofPath",
      a.bank_code AS "bankCode",
      a.bank_reference AS "bankReference",
      a.bank_sender_name AS "bankSenderName",
      a.bank_proof_path AS "bankProofPath",
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

-- ============================================================
-- HISTORY
-- ============================================================

CREATE OR REPLACE FUNCTION get_admission_history()
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
        a.application_number AS id,
        a.id AS "applicationId",
        a.application_number AS "applicationNumber",
        CONCAT(a.last_name, ', ', a.first_name, ' ', COALESCE(a.middle_name, '')) AS student,
        COALESCE(a.student_id_generated, '—') AS "studentId",
        str.code AS strand,
        a.grade_level AS grade,
        INITCAP(a.status) AS status,
        TO_CHAR(COALESCE(a.reviewed_at, a.created_at), 'YYYY-MM-DD') AS date,
        a.email
      FROM admission_applications a
      LEFT JOIN strands str ON str.id = a.strand_id
      WHERE a.status IN ('approved', 'rejected')
      ORDER BY a.reviewed_at DESC NULLS LAST, a.created_at DESC
    ) t
  );
END;
$$;

-- ============================================================
-- REVIEW (lookup by UUID or application number)
-- ============================================================

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
      student_id, last_name, first_name, middle_name, birthdate, password,
      gender, address, contact_number, admission_type, admission_status,
      grade_level, strand_id, scholastic_status, track, is_active
    )
    VALUES (
      v_student_id, v_app.last_name, v_app.first_name, v_app.middle_name,
      v_app.birthdate, v_temp_password, v_app.gender, v_app.address,
      v_app.contact_number, v_app.admission_type, 'approved',
      v_app.grade_level, v_app.strand_id, 'Regular', 'Academic', TRUE
    )
    RETURNING id INTO v_student_uuid;

    INSERT INTO notifications (student_id, title, message, type)
    VALUES (
      v_student_uuid,
      'Welcome to Enrollment Management System',
      'Your admission has been approved. Use your Student ID to sign in to the enrollment portal.',
      'announcement'
    );

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

GRANT EXECUTE ON FUNCTION submit_admission_application TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_pending_admissions TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_admission_detail TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_admission_history TO anon, authenticated;
GRANT EXECUTE ON FUNCTION review_admission_application TO anon, authenticated;
