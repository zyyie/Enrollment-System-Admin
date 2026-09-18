-- Tuition payment module + 1.0–5.0 grade scale (1.0 highest, 3.0 passing, 5.0 failed)
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS enrollment_payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  enrollment_id UUID NOT NULL UNIQUE REFERENCES enrollments(id) ON DELETE CASCADE,
  assessment_amount NUMERIC(12,2) NOT NULL DEFAULT 2500.00,
  amount_paid NUMERIC(12,2) NOT NULL DEFAULT 0,
  balance NUMERIC(12,2) GENERATED ALWAYS AS (GREATEST(assessment_amount - amount_paid, 0)) STORED,
  status TEXT NOT NULL DEFAULT 'unpaid'
    CHECK (status IN ('unpaid', 'pending', 'approved')),
  or_number TEXT,
  payment_date DATE,
  payment_mode TEXT DEFAULT 'cashier',
  notes TEXT,
  approved_by UUID REFERENCES faculty(id),
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_enrollment_payments_status ON enrollment_payments(status);
CREATE INDEX IF NOT EXISTS idx_enrollment_payments_enrollment ON enrollment_payments(enrollment_id);

CREATE OR REPLACE FUNCTION grade_status_from_final(p_final NUMERIC)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN p_final IS NULL THEN 'incomplete'
    WHEN p_final >= 1.0 AND p_final <= 3.0 THEN 'passed'
    ELSE 'failed'
  END;
$$;

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

-- Create payment record when enrollment is approved
CREATE OR REPLACE FUNCTION review_enrollment(
  p_enrollment_id UUID,
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
  v_new_status TEXT;
  v_student UUID;
BEGIN
  SELECT id INTO v_faculty
  FROM faculty WHERE faculty_id = UPPER(TRIM(p_faculty_id)) LIMIT 1;

  v_new_status := CASE
    WHEN LOWER(p_action) = 'approve' THEN 'enrolled'
    WHEN LOWER(p_action) = 'reject' THEN 'rejected'
    ELSE NULL
  END;

  IF v_new_status IS NULL THEN
    RAISE EXCEPTION 'Invalid action';
  END IF;

  UPDATE enrollments e
  SET
    status = v_new_status,
    reviewed_by = v_faculty,
    reviewed_at = NOW(),
    rejection_reason = CASE WHEN v_new_status = 'rejected' THEN p_reason ELSE NULL END,
    updated_at = NOW(),
    enrolled_at = CASE WHEN v_new_status = 'enrolled' THEN NOW() ELSE enrolled_at END
  WHERE e.id = p_enrollment_id
  RETURNING e.student_id INTO v_student;

  IF v_new_status = 'enrolled' THEN
    PERFORM ensure_enrollment_payment(p_enrollment_id);
  END IF;

  IF v_student IS NOT NULL THEN
    PERFORM insert_student_notification(
      v_student,
      CASE WHEN v_new_status = 'enrolled' THEN 'Enrollment Approved' ELSE 'Enrollment Rejected' END,
      CASE WHEN v_new_status = 'enrolled'
        THEN 'Your enrollment has been approved. Please check Payment / Accounts for your tuition assessment.'
        ELSE COALESCE('Your enrollment was rejected. ' || p_reason, 'Your enrollment was rejected. Contact the registrar.')
      END,
      'enrollment'
    );
  END IF;

  RETURN json_build_object('success', TRUE, 'status', v_new_status);
END;
$$;

CREATE OR REPLACE FUNCTION get_student_payment_status(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  result JSON;
BEGIN
  SELECT s.id INTO v_student
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object('found', FALSE, 'message', 'Student not found.');
  END IF;

  SELECT json_build_object(
    'found', TRUE,
    'enrollmentStatus', e.status,
    'payments', COALESCE(json_agg(json_build_object(
      'enrollmentId', e.id,
      'schoolYear', sy.label,
      'semester', sem.name,
      'assessmentAmount', COALESCE(ep.assessment_amount, 0),
      'amountPaid', COALESCE(ep.amount_paid, 0),
      'balance', COALESCE(ep.balance, 0),
      'status', COALESCE(ep.status, 'unpaid'),
      'orNumber', ep.or_number,
      'paymentDate', ep.payment_date,
      'paymentMode', ep.payment_mode,
      'approvedAt', ep.approved_at,
      'notes', ep.notes
    ) ORDER BY sem.code DESC), '[]'::json)
  )
  INTO result
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id
  JOIN school_years sy ON sy.id = sem.school_year_id
  LEFT JOIN enrollment_payments ep ON ep.enrollment_id = e.id
  WHERE e.student_id = v_student
    AND e.status IN ('enrolled', 'approved')
    AND sem.is_current = TRUE
  GROUP BY e.status;

  IF result IS NULL THEN
    RETURN json_build_object(
      'found', TRUE,
      'enrollmentStatus', 'none',
      'payments', '[]'::json,
      'message', 'No active enrollment for the current term.'
    );
  END IF;

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
BEGIN
  SELECT id INTO v_faculty
  FROM faculty WHERE faculty_id = UPPER(TRIM(p_faculty_id)) LIMIT 1;

  SELECT assessment_amount INTO v_assessment
  FROM enrollment_payments
  WHERE enrollment_id = p_enrollment_id;

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
    'Your tuition payment has been approved. You have no remaining balance for this term.',
    'payment'
  );

  RETURN json_build_object(
    'success', TRUE,
    'amountPaid', v_paid,
    'balance', GREATEST(v_assessment - v_paid, 0),
    'status', 'approved'
  );
END;
$$;

-- Backfill payment rows for existing enrolled students (uses admission fee amount)
INSERT INTO enrollment_payments (enrollment_id, assessment_amount, status)
SELECT e.id, resolve_enrollment_assessment_amount(e.id), 'unpaid'
FROM enrollments e
JOIN semesters sem ON sem.id = e.semester_id
WHERE e.status = 'enrolled'
  AND sem.is_current = TRUE
ON CONFLICT (enrollment_id) DO NOTHING;

CREATE OR REPLACE FUNCTION save_student_grades(
  p_enrollment_id UUID,
  p_faculty_id TEXT,
  p_grades JSON
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_faculty UUID;
  v_student UUID;
  v_item JSON;
  v_es_id UUID;
  v_final NUMERIC;
  v_status TEXT;
BEGIN
  SELECT id INTO v_faculty FROM faculty WHERE faculty_id = UPPER(TRIM(p_faculty_id)) LIMIT 1;

  SELECT e.student_id INTO v_student
  FROM enrollments e
  WHERE e.id = p_enrollment_id AND e.status = 'enrolled'
  LIMIT 1;

  IF v_student IS NULL THEN
    RAISE EXCEPTION 'Enrollment not found or not enrolled';
  END IF;

  FOR v_item IN SELECT * FROM json_array_elements(p_grades)
  LOOP
    v_es_id := (v_item->>'enrollmentSubjectId')::UUID;
    v_final := NULLIF(v_item->>'finalGrade', '')::NUMERIC;

    IF v_final IS NOT NULL AND (v_final < 1.0 OR v_final > 5.0) THEN
      RAISE EXCEPTION 'Final grade must be between 1.0 and 5.0';
    END IF;

    v_status := grade_status_from_final(v_final);

    INSERT INTO student_grades (
      enrollment_subject_id, midterm_grade, final_grade, grade_status, encoded_by, updated_at
    )
    VALUES (v_es_id, NULL, v_final, v_status, v_faculty, NOW())
    ON CONFLICT (enrollment_subject_id)
    DO UPDATE SET
      final_grade = EXCLUDED.final_grade,
      grade_status = EXCLUDED.grade_status,
      encoded_by = EXCLUDED.encoded_by,
      updated_at = NOW();

    UPDATE enrollment_subjects
    SET status = CASE WHEN v_status IN ('passed', 'failed') THEN 'completed' ELSE status END
    WHERE id = v_es_id;
  END LOOP;

  PERFORM evaluate_student_progression(v_student);

  RETURN json_build_object('success', TRUE);
END;
$$;

CREATE OR REPLACE FUNCTION get_enrollment_grades_sheet(p_enrollment_id UUID)
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
        es.id AS "enrollmentSubjectId",
        sub.code,
        sub.name AS description,
        es.units,
        sg.final_grade AS "finalGrade",
        COALESCE(sg.grade_status, 'incomplete') AS "gradeStatus",
        CASE
          WHEN sg.final_grade IS NULL THEN 'INC'
          WHEN sg.final_grade >= 1.0 AND sg.final_grade <= 3.0 THEN 'P'
          ELSE 'F'
        END AS "gradeLabel"
      FROM enrollment_subjects es
      JOIN subjects sub ON sub.id = es.subject_id
      LEFT JOIN student_grades sg ON sg.enrollment_subject_id = es.id
      WHERE es.enrollment_id = p_enrollment_id
      ORDER BY sub.code
    ) t
  );
END;
$$;

-- Patch get_student_grades GPA + status for 1.0 scale
CREATE OR REPLACE FUNCTION get_student_grades(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_enrollment_status TEXT;
  v_terms JSON;
BEGIN
  SELECT s.id INTO v_student
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object(
      'enrollmentStatus', 'none',
      'message', 'Student account not found.',
      'terms', '[]'::json
    );
  END IF;

  SELECT e.status INTO v_enrollment_status
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id AND sem.is_current = TRUE
  WHERE e.student_id = v_student
  ORDER BY e.created_at DESC
  LIMIT 1;

  IF v_enrollment_status IS NULL THEN
    RETURN json_build_object(
      'enrollmentStatus', 'none',
      'message', 'You have not enrolled for this semester yet. Go to Enrollment to select your subjects.',
      'terms', '[]'::json
    );
  END IF;

  IF v_enrollment_status = 'pending' THEN
    RETURN json_build_object(
      'enrollmentStatus', 'pending',
      'message', 'Your enrollment is pending admin approval.',
      'terms', '[]'::json
    );
  END IF;

  IF v_enrollment_status = 'rejected' THEN
    RETURN json_build_object(
      'enrollmentStatus', 'rejected',
      'message', 'Your enrollment was not approved. Please contact the registrar office.',
      'terms', '[]'::json
    );
  END IF;

  SELECT COALESCE(json_agg(term_row ORDER BY label DESC, code), '[]'::json)
  INTO v_terms
  FROM (
    SELECT json_build_object(
      'schoolYear', sy.label,
      'semester', sem.name,
      'semesterCode', sem.code,
      'gpa', (
        SELECT ROUND(AVG(sg.final_grade)::numeric, 2)
        FROM enrollment_subjects es2
        LEFT JOIN student_grades sg ON sg.enrollment_subject_id = es2.id
        WHERE es2.enrollment_id = e.id
          AND sg.final_grade IS NOT NULL
          AND sg.grade_status = 'passed'
      ),
      'subjects', (
        SELECT COALESCE(json_agg(json_build_object(
          'code', sub.code,
          'description', sub.name,
          'faculty', COALESCE(NULLIF(TRIM(CONCAT(f.last_name, ', ', f.first_name)), ','), 'TBA'),
          'units', es.units,
          'sectCode', COALESCE(sec.name, ''),
          'finalGrade', sg.final_grade,
          'status', CASE
            WHEN sg.id IS NULL OR sg.final_grade IS NULL THEN 'INC'
            WHEN sg.final_grade >= 1.0 AND sg.final_grade <= 3.0 THEN 'P'
            ELSE 'F'
          END
        ) ORDER BY sub.code), '[]'::json)
        FROM enrollment_subjects es
        JOIN subjects sub ON sub.id = es.subject_id
        LEFT JOIN student_grades sg ON sg.enrollment_subject_id = es.id
        LEFT JOIN class_schedules cs ON cs.id = es.class_schedule_id
        LEFT JOIN faculty f ON f.id = cs.faculty_id
        LEFT JOIN sections sec ON sec.id = cs.section_id
        WHERE es.enrollment_id = e.id
          AND es.status IN ('enrolled', 'completed')
      )
    ) AS term_row,
    sy.label AS label,
    sem.code AS code
    FROM enrollments e
    JOIN students st ON st.id = e.student_id
    JOIN semesters sem ON sem.id = e.semester_id
    JOIN school_years sy ON sy.id = sem.school_year_id
    WHERE st.student_id = UPPER(TRIM(p_student_id))
      AND e.status IN ('approved', 'enrolled')
    GROUP BY e.id, sy.label, sem.name, sem.code
  ) t;

  RETURN json_build_object(
    'enrollmentStatus', v_enrollment_status,
    'message', NULL,
    'terms', v_terms
  );
END;
$$;

GRANT EXECUTE ON FUNCTION resolve_enrollment_assessment_amount(UUID) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_student_payment_status(TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION list_enrollment_payments(TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION approve_enrollment_payment(UUID, TEXT, NUMERIC, TEXT, TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION ensure_enrollment_payment(UUID) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION grade_status_from_final(NUMERIC) TO anon, authenticated, service_role;
