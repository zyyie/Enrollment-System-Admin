-- ============================================================
-- High School Diploma document support
-- Run in Supabase SQL Editor
-- NOTE: For approve errors, run fix-approve-review.sql instead (includes this + student fixes)
-- ============================================================

ALTER TABLE students ADD COLUMN IF NOT EXISTS password TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS scholastic_status TEXT DEFAULT 'Regular';
ALTER TABLE students ADD COLUMN IF NOT EXISTS track TEXT DEFAULT 'Academic';
ALTER TABLE students ADD COLUMN IF NOT EXISTS admission_type TEXT DEFAULT 'new';
ALTER TABLE students ADD COLUMN IF NOT EXISTS admission_status TEXT DEFAULT 'enrolled';

ALTER TABLE admission_applications
  ADD COLUMN IF NOT EXISTS doc_high_school_diploma_path TEXT;

-- Backfill from documents JSON if already uploaded
UPDATE admission_applications
SET doc_high_school_diploma_path = COALESCE(
  doc_high_school_diploma_path,
  NULLIF(documents->>'high_school_diploma', '')
)
WHERE documents ? 'high_school_diploma'
   OR doc_high_school_diploma_path IS NULL;

-- Allow TEXT lookup (UUID or APP-2026-xxxxx)
DROP FUNCTION IF EXISTS get_admission_detail(UUID);

-- ============================================================
-- SUBMIT — save high school diploma path + documents JSON key
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

-- ============================================================
-- PENDING LIST — include diploma in API response
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

-- ============================================================
-- DETAIL — include diploma (UUID or APP number)
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

GRANT EXECUTE ON FUNCTION submit_admission_application TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_pending_admissions TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_admission_detail TO anon, authenticated;
