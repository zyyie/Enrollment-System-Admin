-- Sync tuition assessment with enrollment/admission payment amount (default PHP 2,500)
-- Run in Supabase SQL Editor if Payment Approval shows 15,000 but enrollment fee is 2,500

CREATE OR REPLACE FUNCTION resolve_enrollment_assessment_amount(p_enrollment_id UUID)
RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_amount NUMERIC;
  v_student_text TEXT;
BEGIN
  SELECT st.student_id INTO v_student_text
  FROM enrollments e
  JOIN students st ON st.id = e.student_id
  WHERE e.id = p_enrollment_id;

  IF v_student_text IS NOT NULL THEN
    SELECT a.payment_amount INTO v_amount
    FROM admission_applications a
    WHERE UPPER(TRIM(a.student_id_generated)) = UPPER(TRIM(v_student_text))
      AND a.payment_amount IS NOT NULL
      AND a.payment_amount > 0
    ORDER BY a.created_at DESC
    LIMIT 1;
  END IF;

  -- Must match ENROLLMENT_FEE in server .env / js/config.js (default 2500)
  RETURN COALESCE(v_amount, 2500.00);
END;
$$;

CREATE OR REPLACE FUNCTION ensure_enrollment_payment(p_enrollment_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_assessment NUMERIC := resolve_enrollment_assessment_amount(p_enrollment_id);
BEGIN
  INSERT INTO enrollment_payments (enrollment_id, assessment_amount, status)
  VALUES (p_enrollment_id, v_assessment, 'unpaid')
  ON CONFLICT (enrollment_id) DO UPDATE SET
    assessment_amount = EXCLUDED.assessment_amount,
    updated_at = NOW()
  WHERE enrollment_payments.status IN ('unpaid', 'pending')
    AND COALESCE(enrollment_payments.amount_paid, 0) = 0;
END;
$$;

-- Fix existing rows that used the old 15,000 default
UPDATE enrollment_payments ep
SET
  assessment_amount = resolve_enrollment_assessment_amount(ep.enrollment_id),
  updated_at = NOW()
WHERE ep.status IN ('unpaid', 'pending')
  AND COALESCE(ep.amount_paid, 0) = 0
  AND (
    ep.assessment_amount = 15000
    OR ep.assessment_amount <> resolve_enrollment_assessment_amount(ep.enrollment_id)
  );

-- Alter table default for new installs
ALTER TABLE enrollment_payments
  ALTER COLUMN assessment_amount SET DEFAULT 2500.00;

GRANT EXECUTE ON FUNCTION resolve_enrollment_assessment_amount(UUID) TO anon, authenticated, service_role;
