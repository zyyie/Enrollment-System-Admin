-- Registration form email workflow: send COR only after payment approval.
-- Run in Supabase SQL Editor after tuition-payment-and-grades.sql

ALTER TABLE enrollment_payments
  ADD COLUMN IF NOT EXISTS registration_form_email_sent BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS registration_form_email_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS registration_form_email_error TEXT;

CREATE OR REPLACE FUNCTION approve_enrollment_payment(
  p_enrollment_id UUID,
  p_faculty_id TEXT,
  p_amount_paid NUMERIC DEFAULT NULL,
  p_or_number TEXT DEFAULT NULL,
  p_payment_mode TEXT DEFAULT 'cashier',
  p_notes TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_faculty UUID;
  v_assessment NUMERIC;
  v_paid NUMERIC;
  v_payment_status TEXT;
  v_email_sent BOOLEAN;
  v_enrollment_status TEXT;
  v_student_text TEXT;
  v_first_name TEXT;
  v_last_name TEXT;
  v_middle_name TEXT;
  v_email TEXT;
  v_grade_level TEXT;
  v_strand_code TEXT;
  v_school_year TEXT;
  v_semester_name TEXT;
  v_application_number TEXT;
BEGIN
  SELECT id INTO v_faculty
  FROM faculty WHERE faculty_id = UPPER(TRIM(p_faculty_id)) LIMIT 1;

  SELECT
    e.status,
    st.student_id,
    st.first_name,
    st.last_name,
    st.middle_name,
    st.grade_level,
    str.code,
    sy.label,
    sem.name,
    ep.status,
    COALESCE(ep.registration_form_email_sent, FALSE),
    ep.assessment_amount
  INTO
    v_enrollment_status,
    v_student_text,
    v_first_name,
    v_last_name,
    v_middle_name,
    v_grade_level,
    v_strand_code,
    v_school_year,
    v_semester_name,
    v_payment_status,
    v_email_sent,
    v_assessment
  FROM enrollments e
  JOIN students st ON st.id = e.student_id
  LEFT JOIN strands str ON str.id = st.strand_id
  JOIN semesters sem ON sem.id = e.semester_id
  JOIN school_years sy ON sy.id = sem.school_year_id
  LEFT JOIN enrollment_payments ep ON ep.enrollment_id = e.id
  WHERE e.id = p_enrollment_id
  FOR UPDATE OF e;

  IF v_enrollment_status IS NULL THEN
    RAISE EXCEPTION 'Enrollment not found';
  END IF;

  IF v_enrollment_status <> 'enrolled' THEN
    RAISE EXCEPTION 'Enrollment must be approved before payment can be approved';
  END IF;

  SELECT a.email, a.application_number
  INTO v_email, v_application_number
  FROM admission_applications a
  WHERE UPPER(TRIM(a.student_id_generated)) = UPPER(TRIM(v_student_text))
    AND a.status = 'approved'
  ORDER BY a.reviewed_at DESC NULLS LAST, a.created_at DESC
  LIMIT 1;

  IF v_payment_status = 'approved' THEN
    RETURN json_build_object(
      'success', TRUE,
      'alreadyApproved', TRUE,
      'enrollmentStatus', v_enrollment_status,
      'paymentStatus', 'approved',
      'registrationFormEmailSent', COALESCE(v_email_sent, FALSE),
      'studentId', v_student_text,
      'firstName', v_first_name,
      'lastName', v_last_name,
      'middleName', v_middle_name,
      'email', v_email,
      'applicationNumber', v_application_number,
      'gradeLevel', v_grade_level,
      'strandCode', v_strand_code,
      'schoolYear', v_school_year,
      'semester', v_semester_name,
      'amountPaid', (SELECT amount_paid FROM enrollment_payments WHERE enrollment_id = p_enrollment_id),
      'balance', (SELECT balance FROM enrollment_payments WHERE enrollment_id = p_enrollment_id),
      'status', 'approved'
    );
  END IF;

  IF v_assessment IS NULL THEN
    PERFORM ensure_enrollment_payment(p_enrollment_id);
    SELECT assessment_amount INTO v_assessment
    FROM enrollment_payments
    WHERE enrollment_id = p_enrollment_id;
  END IF;

  v_paid := COALESCE(p_amount_paid, v_assessment);

  UPDATE enrollment_payments
  SET
    amount_paid = v_paid,
    status = 'approved',
    or_number = NULLIF(TRIM(p_or_number), ''),
    payment_mode = COALESCE(NULLIF(TRIM(p_payment_mode), ''), 'cashier'),
    notes = NULLIF(TRIM(p_notes), ''),
    payment_date = CURRENT_DATE,
    approved_by = v_faculty,
    approved_at = NOW(),
    updated_at = NOW()
  WHERE enrollment_id = p_enrollment_id;

  PERFORM insert_student_notification(
    (SELECT student_id FROM enrollments WHERE id = p_enrollment_id LIMIT 1),
    'Payment Approved',
    'Your tuition payment has been approved. Your Registration Certificate will be emailed shortly.',
    'payment'
  );

  RETURN json_build_object(
    'success', TRUE,
    'alreadyApproved', FALSE,
    'enrollmentStatus', v_enrollment_status,
    'paymentStatus', 'approved',
    'registrationFormEmailSent', COALESCE(v_email_sent, FALSE),
    'studentId', v_student_text,
    'firstName', v_first_name,
    'lastName', v_last_name,
    'middleName', v_middle_name,
    'email', v_email,
    'applicationNumber', v_application_number,
    'gradeLevel', v_grade_level,
    'strandCode', v_strand_code,
    'schoolYear', v_school_year,
    'semester', v_semester_name,
    'amountPaid', v_paid,
    'balance', GREATEST(v_assessment - v_paid, 0),
    'status', 'approved'
  );
END;
$$;

CREATE OR REPLACE FUNCTION mark_registration_form_email_sent(p_enrollment_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_updated UUID;
BEGIN
  UPDATE enrollment_payments
  SET
    registration_form_email_sent = TRUE,
    registration_form_email_sent_at = NOW(),
    registration_form_email_error = NULL,
    updated_at = NOW()
  WHERE enrollment_id = p_enrollment_id
    AND status = 'approved'
    AND registration_form_email_sent = FALSE
  RETURNING id INTO v_updated;

  RETURN json_build_object(
    'success', v_updated IS NOT NULL,
    'marked', v_updated IS NOT NULL
  );
END;
$$;

CREATE OR REPLACE FUNCTION mark_registration_form_email_failed(
  p_enrollment_id UUID,
  p_error TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE enrollment_payments
  SET
    registration_form_email_error = LEFT(COALESCE(NULLIF(TRIM(p_error), ''), 'Email delivery failed'), 500),
    updated_at = NOW()
  WHERE enrollment_id = p_enrollment_id
    AND status = 'approved'
    AND registration_form_email_sent = FALSE;

  RETURN json_build_object('success', TRUE);
END;
$$;

CREATE OR REPLACE FUNCTION list_enrollment_payments(p_status TEXT DEFAULT NULL)
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
        ep.id AS "paymentId",
        e.id AS "enrollmentId",
        st.student_id AS "studentId",
        CONCAT(st.last_name, ', ', st.first_name) AS student,
        st.grade_level AS "gradeLevel",
        str.code AS strand,
        sem.name AS semester,
        sy.label AS "schoolYear",
        ep.assessment_amount AS "assessmentAmount",
        ep.amount_paid AS "amountPaid",
        ep.balance,
        ep.status,
        ep.or_number AS "orNumber",
        ep.payment_mode AS "paymentMode",
        ep.notes,
        COALESCE(ep.registration_form_email_sent, FALSE) AS "registrationFormEmailSent",
        ep.registration_form_email_sent_at AS "registrationFormEmailSentAt",
        ep.registration_form_email_error AS "registrationFormEmailError",
        TO_CHAR(ep.created_at, 'Mon DD, YYYY') AS "createdAt"
      FROM enrollment_payments ep
      JOIN enrollments e ON e.id = ep.enrollment_id
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      JOIN semesters sem ON sem.id = e.semester_id
      JOIN school_years sy ON sy.id = sem.school_year_id
      WHERE e.status = 'enrolled'
        AND sem.is_current = TRUE
        AND (p_status IS NULL OR ep.status = p_status)
      ORDER BY
        CASE ep.status
          WHEN 'pending' THEN 0
          WHEN 'unpaid' THEN 1
          ELSE 2
        END,
        st.last_name, st.first_name
    ) t
  );
END;
$$;

GRANT EXECUTE ON FUNCTION mark_registration_form_email_sent(UUID) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION mark_registration_form_email_failed(UUID, TEXT) TO anon, authenticated, service_role;
