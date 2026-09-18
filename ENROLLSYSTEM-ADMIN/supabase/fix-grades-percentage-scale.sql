-- Percentage grading scale (DepEd-style descriptors)
-- Run in Supabase SQL Editor

CREATE OR REPLACE FUNCTION grade_descriptor_from_final(p_final NUMERIC)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN p_final IS NULL THEN NULL
    WHEN p_final >= 90 THEN 'Outstanding'
    WHEN p_final >= 85 THEN 'Very Satisfactory'
    WHEN p_final >= 80 THEN 'Satisfactory'
    WHEN p_final >= 75 THEN 'Fairly Satisfactory'
    ELSE 'Did Not Meet Expectations (Failed)'
  END;
$$;

CREATE OR REPLACE FUNCTION grade_status_from_final(p_final NUMERIC)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN p_final IS NULL THEN 'incomplete'
    WHEN p_final >= 75 THEN 'passed'
    ELSE 'failed'
  END;
$$;

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

    IF v_final IS NOT NULL AND (v_final < 0 OR v_final > 100) THEN
      RAISE EXCEPTION 'Final grade must be between 0 and 100';
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
        grade_descriptor_from_final(sg.final_grade) AS "gradeDescriptor",
        CASE
          WHEN sg.final_grade IS NULL THEN 'INC'
          WHEN sg.final_grade >= 75 THEN 'P'
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
          'descriptor', grade_descriptor_from_final(sg.final_grade),
          'status', CASE
            WHEN sg.id IS NULL OR sg.final_grade IS NULL THEN 'INC'
            WHEN sg.final_grade >= 75 THEN 'P'
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

GRANT EXECUTE ON FUNCTION grade_descriptor_from_final(NUMERIC) TO anon, authenticated, service_role;
