-- GCash integrated payment fields for admission applications
-- Run in Supabase SQL Editor

ALTER TABLE admission_applications
  ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'pending'
    CHECK (payment_status IN ('pending', 'paid', 'failed', 'waived')),
  ADD COLUMN IF NOT EXISTS payment_session_id TEXT,
  ADD COLUMN IF NOT EXISTS payment_amount NUMERIC(10, 2);

-- Update submit function to store payment gateway data
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
    application_number,
    last_name,
    first_name,
    middle_name,
    birthdate,
    gender,
    address,
    contact_number,
    email,
    grade_level,
    strand_id,
    admission_type,
    payment_mode,
    gcash_reference,
    gcash_proof_path,
    payment_status,
    payment_session_id,
    payment_amount,
    documents,
    status
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
    NULLIF(p_payload->>'gcashProofPath', ''),
    COALESCE(p_payload->>'paymentStatus', 'pending'),
    NULLIF(p_payload->>'paymentSessionId', ''),
    NULLIF(p_payload->>'paymentAmount', '')::NUMERIC,
    COALESCE(p_payload->'documents', '{}'::json),
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
