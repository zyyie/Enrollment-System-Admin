-- GCash QR payment — sender name field
-- Run in Supabase SQL Editor

ALTER TABLE admission_applications
  ADD COLUMN IF NOT EXISTS gcash_sender_name TEXT;

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
BEGIN
  SELECT COUNT(*) + 1 INTO v_count FROM admission_applications;
  v_app_number := 'APP-' || TO_CHAR(NOW(), 'YYYY') || '-' || LPAD(v_count::TEXT, 5, '0');

  INSERT INTO admission_applications (
    application_number, last_name, first_name, middle_name, birthdate, gender,
    address, contact_number, email, grade_level, strand_id, admission_type,
    payment_mode, gcash_reference, gcash_sender_name, gcash_proof_path,
    payment_status, payment_amount, documents, status
  )
  VALUES (
    v_app_number,
    UPPER(TRIM(p_payload->>'lastName')),
    UPPER(TRIM(p_payload->>'firstName')),
    NULLIF(UPPER(TRIM(p_payload->>'middleName')), ''),
    (p_payload->>'birthdate')::DATE,
    p_payload->>'gender',
    p_payload->>'address',
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
    COALESCE(p_payload->'documents', '{}'::json),
    'pending'
  )
  RETURNING id INTO v_id;

  RETURN json_build_object('success', TRUE, 'applicationId', v_id, 'applicationNumber', v_app_number);
END;
$$;

-- Return sender name in pending admissions list
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
        a.payment_amount AS "paymentAmount",
        a.status,
        TO_CHAR(a.created_at, 'Mon DD, YYYY HH12:MI AM') AS date,
        a.documents
      FROM admission_applications a
      LEFT JOIN strands str ON str.id = a.strand_id
      WHERE a.status = 'pending'
      ORDER BY a.created_at DESC
    ) t
  );
END;
$$;
