-- Enrollment payment at subject submit + admin visibility
-- Run in Supabase SQL Editor after tuition-payment-and-grades.sql

ALTER TABLE enrollment_payments
  ADD COLUMN IF NOT EXISTS gcash_reference TEXT,
  ADD COLUMN IF NOT EXISTS gcash_sender_name TEXT,
  ADD COLUMN IF NOT EXISTS gcash_proof_path TEXT,
  ADD COLUMN IF NOT EXISTS registration_form_email_sent BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS registration_form_email_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS registration_form_email_error TEXT;

CREATE OR REPLACE FUNCTION record_enrollment_payment_submit(
  p_enrollment_id UUID,
  p_payment_mode TEXT DEFAULT 'cashier',
  p_amount_paid NUMERIC DEFAULT NULL,
  p_gcash_reference TEXT DEFAULT NULL,
  p_gcash_sender_name TEXT DEFAULT NULL,
  p_gcash_proof_path TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_assessment NUMERIC;
  v_mode TEXT;
  v_status TEXT;
  v_paid NUMERIC;
BEGIN
  IF p_enrollment_id IS NULL THEN
    RAISE EXCEPTION 'enrollment id is required';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM enrollments WHERE id = p_enrollment_id) THEN
    RAISE EXCEPTION 'Enrollment not found';
  END IF;

  v_assessment := resolve_enrollment_assessment_amount(p_enrollment_id);
  v_mode := LOWER(TRIM(COALESCE(p_payment_mode, 'cashier')));
  IF v_mode NOT IN ('gcash', 'cashier', 'bank') THEN
    v_mode := 'cashier';
  END IF;

  v_status := CASE WHEN v_mode = 'gcash' THEN 'pending' ELSE 'unpaid' END;
  v_paid := CASE
    WHEN v_mode = 'gcash' THEN COALESCE(p_amount_paid, v_assessment)
    ELSE 0
  END;

  INSERT INTO enrollment_payments (
    enrollment_id,
    assessment_amount,
    amount_paid,
    status,
    payment_mode,
    gcash_reference,
    gcash_sender_name,
    gcash_proof_path,
    updated_at
  )
  VALUES (
    p_enrollment_id,
    v_assessment,
    v_paid,
    v_status,
    v_mode,
    NULLIF(TRIM(p_gcash_reference), ''),
    NULLIF(TRIM(p_gcash_sender_name), ''),
    NULLIF(TRIM(p_gcash_proof_path), ''),
    NOW()
  )
  ON CONFLICT (enrollment_id) DO UPDATE SET
    assessment_amount = EXCLUDED.assessment_amount,
    amount_paid = EXCLUDED.amount_paid,
    status = EXCLUDED.status,
    payment_mode = EXCLUDED.payment_mode,
    gcash_reference = EXCLUDED.gcash_reference,
    gcash_sender_name = EXCLUDED.gcash_sender_name,
    gcash_proof_path = EXCLUDED.gcash_proof_path,
    updated_at = NOW()
  WHERE enrollment_payments.status IN ('unpaid', 'pending');

  RETURN json_build_object(
    'success', TRUE,
    'enrollmentId', p_enrollment_id,
    'paymentMode', v_mode,
    'status', v_status,
    'amountPaid', v_paid,
    'assessmentAmount', v_assessment
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_pending_enrollments()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN COALESCE((
    SELECT json_agg(row_to_json(t))
    FROM (
      SELECT
        e.id,
        e.enrollment_number AS "enrollmentNumber",
        CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(LEFT(st.middle_name, 1) || '.', '')) AS student,
        st.student_id AS "studentId",
        str.code AS strand,
        st.grade_level AS grade,
        e.status,
        TO_CHAR(COALESCE(e.enrolled_at, e.created_at), 'Mon DD, YYYY HH12:MI AM') AS date,
        e.total_units AS "totalUnits",
        sem.name AS semester,
        sy.label AS "schoolYear",
        COALESCE(ep.payment_mode, 'cashier') AS "paymentMode",
        COALESCE(ep.status, 'unpaid') AS "paymentStatus",
        ep.gcash_reference AS "gcashReference",
        ep.gcash_sender_name AS "gcashSenderName",
        ep.amount_paid AS "amountPaid",
        ep.assessment_amount AS "assessmentAmount"
      FROM enrollments e
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      JOIN semesters sem ON sem.id = e.semester_id
      JOIN school_years sy ON sy.id = sem.school_year_id
      LEFT JOIN enrollment_payments ep ON ep.enrollment_id = e.id
      WHERE e.status = 'pending'
      ORDER BY COALESCE(e.enrolled_at, e.created_at) DESC
    ) t
  ), '[]'::json);
END;
$$;

CREATE OR REPLACE FUNCTION get_enrollment_detail(p_enrollment_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_build_object(
    'id', e.id,
    'enrollmentNumber', e.enrollment_number,
    'status', e.status,
    'totalUnits', e.total_units,
    'submittedAt', TO_CHAR(e.created_at, 'Mon DD, YYYY HH12:MI AM'),
    'student', json_build_object(
      'id', st.student_id,
      'name', CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(st.middle_name, '')),
      'gradeLevel', st.grade_level,
      'strand', str.code,
      'strandFull', str.name,
      'section', COALESCE(sec.name, ''),
      'progressionStatus', st.progression_status,
      'accountStatus', st.account_status
    ),
    'term', json_build_object(
      'schoolYear', sy.label,
      'semester', sem.name,
      'semesterCode', sem.code
    ),
    'subjects', (
      SELECT COALESCE(json_agg(json_build_object(
        'code', sub.code,
        'description', sub.name,
        'units', es.units,
        'schedule', es.schedule_label
      ) ORDER BY sub.code), '[]'::json)
      FROM enrollment_subjects es
      JOIN subjects sub ON sub.id = es.subject_id
      WHERE es.enrollment_id = e.id
    ),
    'payment', (
      SELECT json_build_object(
        'paymentMode', COALESCE(ep.payment_mode, 'cashier'),
        'status', COALESCE(ep.status, 'unpaid'),
        'assessmentAmount', COALESCE(ep.assessment_amount, resolve_enrollment_assessment_amount(e.id)),
        'amountPaid', COALESCE(ep.amount_paid, 0),
        'balance', COALESCE(ep.balance, resolve_enrollment_assessment_amount(e.id)),
        'gcashReference', ep.gcash_reference,
        'gcashSenderName', ep.gcash_sender_name,
        'gcashProofPath', ep.gcash_proof_path,
        'notes', ep.notes,
        'orNumber', ep.or_number
      )
      FROM enrollment_payments ep
      WHERE ep.enrollment_id = e.id
      LIMIT 1
    )
  )
  INTO result
  FROM enrollments e
  JOIN students st ON st.id = e.student_id
  LEFT JOIN strands str ON str.id = st.strand_id
  LEFT JOIN sections sec ON sec.id = st.section_id
  JOIN semesters sem ON sem.id = e.semester_id
  JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE e.id = p_enrollment_id;

  RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION list_enrollment_payments(p_status TEXT DEFAULT NULL)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  PERFORM ensure_enrollment_payment(e.id)
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id AND sem.is_current = TRUE
  WHERE e.status = 'enrolled';

  RETURN (
    SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
    FROM (
      SELECT
        ep.id AS "paymentId",
        e.id AS "enrollmentId",
        st.student_id AS "studentId",
        CONCAT(st.last_name, ', ', st.first_name) AS student,
        st.grade_level AS "gradeLevel",
        str.code AS strand,
        sem.name AS semester,
        sy.label AS "schoolYear",
        COALESCE(ep.assessment_amount, resolve_enrollment_assessment_amount(e.id)) AS "assessmentAmount",
        COALESCE(ep.amount_paid, 0) AS "amountPaid",
        COALESCE(ep.balance, resolve_enrollment_assessment_amount(e.id)) AS balance,
        COALESCE(ep.status, 'unpaid') AS status,
        ep.or_number AS "orNumber",
        ep.payment_mode AS "paymentMode",
        ep.gcash_reference AS "gcashReference",
        ep.gcash_sender_name AS "gcashSenderName",
        ep.gcash_proof_path AS "gcashProofPath",
        ep.notes,
        COALESCE(ep.registration_form_email_sent, FALSE) AS "registrationFormEmailSent",
        ep.registration_form_email_sent_at AS "registrationFormEmailSentAt",
        ep.registration_form_email_error AS "registrationFormEmailError",
        TO_CHAR(COALESCE(ep.created_at, e.enrolled_at, e.updated_at), 'Mon DD, YYYY') AS "createdAt"
      FROM enrollments e
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      JOIN semesters sem ON sem.id = e.semester_id AND sem.is_current = TRUE
      JOIN school_years sy ON sy.id = sem.school_year_id
      LEFT JOIN enrollment_payments ep ON ep.enrollment_id = e.id
      WHERE e.status = 'enrolled'
        AND (p_status IS NULL OR COALESCE(ep.status, 'unpaid') = p_status)
      ORDER BY
        CASE COALESCE(ep.status, 'unpaid')
          WHEN 'pending' THEN 0
          WHEN 'unpaid' THEN 1
          ELSE 2
        END,
        st.last_name, st.first_name
    ) t
  );
END;
$$;

GRANT EXECUTE ON FUNCTION record_enrollment_payment_submit(UUID, TEXT, NUMERIC, TEXT, TEXT, TEXT) TO anon, authenticated, service_role;
