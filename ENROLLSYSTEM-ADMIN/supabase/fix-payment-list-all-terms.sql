-- Show unpaid/pending payments from ALL terms (not only current semester).
-- Run in Supabase SQL Editor after enrollment-payment-submit.sql

CREATE OR REPLACE FUNCTION list_enrollment_payments(
  p_status TEXT DEFAULT NULL,
  p_scope TEXT DEFAULT 'needs_action'
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  PERFORM ensure_enrollment_payment(e.id)
  FROM enrollments e
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
        sem.code AS "semesterCode",
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
        COALESCE(sem.is_current, FALSE) AS "isCurrentTerm",
        TO_CHAR(COALESCE(ep.created_at, e.enrolled_at, e.updated_at), 'Mon DD, YYYY') AS "createdAt"
      FROM enrollments e
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      JOIN semesters sem ON sem.id = e.semester_id
      JOIN school_years sy ON sy.id = sem.school_year_id
      LEFT JOIN enrollment_payments ep ON ep.enrollment_id = e.id
      WHERE e.status = 'enrolled'
        AND (
          (p_scope = 'needs_action' AND COALESCE(ep.status, 'unpaid') IN ('unpaid', 'pending'))
          OR (p_scope = 'current_term' AND COALESCE(sem.is_current, FALSE) = TRUE)
          OR (p_scope = 'all_terms')
        )
        AND (p_status IS NULL OR COALESCE(ep.status, 'unpaid') = p_status)
      ORDER BY
        CASE WHEN COALESCE(sem.is_current, FALSE) THEN 1 ELSE 0 END,
        CASE sem.code WHEN '1st' THEN 0 WHEN '2nd' THEN 1 ELSE 2 END,
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

GRANT EXECUTE ON FUNCTION list_enrollment_payments(TEXT, TEXT) TO anon, authenticated, service_role;
