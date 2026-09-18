-- ============================================================
-- Separate admission document columns (4 required files)
-- Run in Supabase SQL Editor after fix-save.sql
-- ============================================================

ALTER TABLE admission_applications
  ADD COLUMN IF NOT EXISTS doc_form_138_path TEXT,
  ADD COLUMN IF NOT EXISTS doc_form_137_path TEXT,
  ADD COLUMN IF NOT EXISTS doc_good_moral_path TEXT,
  ADD COLUMN IF NOT EXISTS doc_birth_certificate_path TEXT;

-- Copy paths from existing JSONB documents column
UPDATE admission_applications
SET
  doc_form_138_path = COALESCE(doc_form_138_path, documents->>'form_138'),
  doc_form_137_path = COALESCE(doc_form_137_path, documents->>'form_137'),
  doc_good_moral_path = COALESCE(doc_good_moral_path, documents->>'good_moral'),
  doc_birth_certificate_path = COALESCE(doc_birth_certificate_path, documents->>'birth_certificate')
WHERE documents IS NOT NULL AND documents <> '{}'::jsonb;

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
BEGIN
  SELECT COUNT(*) + 1 INTO v_count FROM admission_applications;
  v_app_number := 'APP-' || TO_CHAR(NOW(), 'YYYY') || '-' || LPAD(v_count::TEXT, 5, '0');

  v_docs := COALESCE(p_payload->'documents', '{}'::json);

  INSERT INTO admission_applications (
    application_number, last_name, first_name, middle_name, birthdate, gender,
    address, contact_number, email, grade_level, strand_id, admission_type,
    payment_mode, gcash_reference, gcash_sender_name, gcash_proof_path,
    payment_status, payment_amount,
    doc_form_138_path, doc_form_137_path, doc_good_moral_path, doc_birth_certificate_path,
    documents, status
  )
  VALUES (
    v_app_number,
    UPPER(TRIM(p_payload->>'lastName')),
    UPPER(TRIM(p_payload->>'firstName')),
    NULLIF(UPPER(TRIM(p_payload->>'middleName')), ''),
    (p_payload->>'birthdate')::DATE,
    NULLIF(p_payload->>'gender', ''),
    NULLIF(p_payload->>'address', ''),
    p_payload->>'contactNumber',
    LOWER(TRIM(p_payload->>'email')),
    p_payload->>'gradeLevel',
    COALESCE(
      NULLIF(p_payload->>'strandId', '')::UUID,
      (SELECT id FROM strands WHERE code = UPPER(TRIM(p_payload->>'strandCode')) LIMIT 1)
    ),
    COALESCE(p_payload->>'admissionType', 'new'),
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
    jsonb_strip_nulls(jsonb_build_object(
      'form_138', NULLIF(COALESCE(p_payload->>'docForm138Path', v_docs->>'form_138'), ''),
      'form_137', NULLIF(COALESCE(p_payload->>'docForm137Path', v_docs->>'form_137'), ''),
      'good_moral', NULLIF(COALESCE(p_payload->>'docGoodMoralPath', v_docs->>'good_moral'), ''),
      'birth_certificate', NULLIF(COALESCE(p_payload->>'docBirthCertificatePath', v_docs->>'birth_certificate'), '')
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
        CONCAT(a.last_name, ', ', a.first_name, ' ', COALESCE(LEFT(a.middle_name, 1) || '.', '')) AS student,
        a.email,
        a.contact_number AS "contactNumber",
        str.code AS strand,
        a.grade_level AS grade,
        a.payment_mode AS "paymentMode",
        a.gcash_reference AS "gcashReference",
        a.gcash_sender_name AS "gcashSenderName",
        a.gcash_proof_path AS "gcashProofPath",
        a.payment_amount AS "paymentAmount",
        a.status,
        TO_CHAR(a.created_at, 'Mon DD, YYYY HH12:MI AM') AS date,
        a.doc_form_138_path AS "docForm138Path",
        a.doc_form_137_path AS "docForm137Path",
        a.doc_good_moral_path AS "docGoodMoralPath",
        a.doc_birth_certificate_path AS "docBirthCertificatePath",
        COALESCE(
          NULLIF(a.documents, '{}'::jsonb),
          jsonb_strip_nulls(jsonb_build_object(
            'form_138', a.doc_form_138_path,
            'form_137', a.doc_form_137_path,
            'good_moral', a.doc_good_moral_path,
            'birth_certificate', a.doc_birth_certificate_path
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

GRANT EXECUTE ON FUNCTION submit_admission_application TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_pending_admissions TO anon, authenticated;
