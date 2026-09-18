-- Four-stage SHS enrollment lifecycle (G11-1st → G11-2nd → G12-1st → G12-2nd → COMPLETED)
-- Run entire script in Supabase SQL Editor.

-- ── Helpers ─────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION find_stage_enrollment(
  p_student_id UUID,
  p_grade_level TEXT,
  p_semester_code TEXT
)
RETURNS TABLE (
  enrollment_id UUID,
  enrollment_status TEXT,
  payment_status TEXT,
  total_subjects INT,
  graded_subjects INT,
  failed_subjects INT
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.status,
    COALESCE(ep.status, 'unpaid')::TEXT,
    COUNT(es.id)::INT AS total_subjects,
    COUNT(*) FILTER (
      WHERE sg.id IS NOT NULL
        AND sg.final_grade IS NOT NULL
        AND sg.grade_status <> 'incomplete'
    )::INT AS graded_subjects,
    COUNT(*) FILTER (WHERE sg.grade_status = 'failed')::INT AS failed_subjects
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id
  JOIN enrollment_subjects es ON es.enrollment_id = e.id
  JOIN subjects sub ON sub.id = es.subject_id
  LEFT JOIN enrollment_payments ep ON ep.enrollment_id = e.id
  LEFT JOIN student_grades sg ON sg.enrollment_subject_id = es.id
  WHERE e.student_id = p_student_id
    AND sem.code = p_semester_code
    AND sub.grade_level = p_grade_level
    AND e.status IN ('pending', 'approved', 'enrolled', 'rejected')
  GROUP BY e.id, e.status, ep.status
  ORDER BY
    CASE e.status WHEN 'enrolled' THEN 0 WHEN 'approved' THEN 1 WHEN 'pending' THEN 2 ELSE 9 END,
    e.created_at DESC
  LIMIT 1;
END;
$$;

CREATE OR REPLACE FUNCTION is_stage_complete(
  p_student_id UUID,
  p_grade_level TEXT,
  p_semester_code TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_row RECORD;
BEGIN
  SELECT * INTO v_row
  FROM find_stage_enrollment(p_student_id, p_grade_level, p_semester_code);

  IF v_row.enrollment_id IS NULL THEN
    RETURN FALSE;
  END IF;

  IF v_row.enrollment_status <> 'enrolled' THEN
    RETURN FALSE;
  END IF;

  IF COALESCE(v_row.payment_status, 'unpaid') <> 'approved' THEN
    RETURN FALSE;
  END IF;

  IF COALESCE(v_row.total_subjects, 0) = 0 THEN
    RETURN FALSE;
  END IF;

  IF COALESCE(v_row.graded_subjects, 0) < v_row.total_subjects THEN
    RETURN FALSE;
  END IF;

  RETURN TRUE;
END;
$$;

CREATE OR REPLACE FUNCTION student_has_g11_history(p_student_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM students s
    WHERE s.id = p_student_id AND COALESCE(s.grade11_completed, FALSE) = TRUE
  ) THEN
    RETURN TRUE;
  END IF;

  RETURN EXISTS (
    SELECT 1 FROM find_stage_enrollment(p_student_id, 'Grade 11', '1st')
    WHERE enrollment_id IS NOT NULL
  ) OR EXISTS (
    SELECT 1 FROM find_stage_enrollment(p_student_id, 'Grade 11', '2nd')
    WHERE enrollment_id IS NOT NULL
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_student_lifecycle_state(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_progression TEXT;
  v_grade_level TEXT;
  v_stages TEXT[] := ARRAY['g11_1st', 'g11_2nd', 'g12_1st', 'g12_2nd'];
  v_grades TEXT[] := ARRAY['Grade 11', 'Grade 11', 'Grade 12', 'Grade 12'];
  v_sems TEXT[] := ARRAY['1st', '2nd', '1st', '2nd'];
  v_labels TEXT[] := ARRAY[
    'Grade 11 — 1st Semester',
    'Grade 11 — 2nd Semester',
    'Grade 12 — 1st Semester',
    'Grade 12 — 2nd Semester'
  ];
  v_i INT;
  v_row RECORD;
  v_complete BOOLEAN;
  v_next_stage TEXT := NULL;
  v_next_label TEXT := NULL;
  v_completed TEXT[] := ARRAY[]::TEXT[];
  v_blocked_reason TEXT := NULL;
  v_start_i INT := 1;
  v_end_i INT := 4;
  v_direct_g12 BOOLEAN := FALSE;
  v_required_count INT := 4;
BEGIN
  SELECT s.id, s.progression_status, s.grade_level
  INTO v_student, v_progression, v_grade_level
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object(
      'found', FALSE,
      'lifecycleStage', NULL,
      'nextStage', 'g11_1st',
      'nextStageLabel', 'Grade 11 — 1st Semester',
      'completedStages', '[]'::json,
      'isCompleted', FALSE
    );
  END IF;

  v_direct_g12 := v_grade_level = 'Grade 12' AND NOT student_has_g11_history(v_student);
  IF v_direct_g12 THEN
    v_start_i := 3;
    v_end_i := 4;
    v_required_count := 2;
  END IF;

  IF v_progression = 'graduated' THEN
    RETURN json_build_object(
      'found', TRUE,
      'lifecycleStage', 'completed',
      'nextStage', NULL,
      'nextStageLabel', 'Grade 12 — 2nd Semester Completed',
      'completedStages', to_json(v_stages),
      'isCompleted', TRUE,
      'progressionStatus', v_progression,
      'gradeLevel', v_grade_level
    );
  END IF;

  FOR v_i IN v_start_i..v_end_i LOOP
    v_complete := is_stage_complete(v_student, v_grades[v_i], v_sems[v_i]);

    IF v_complete THEN
      v_completed := array_append(v_completed, v_stages[v_i]);
      CONTINUE;
    END IF;

    SELECT * INTO v_row
    FROM find_stage_enrollment(v_student, v_grades[v_i], v_sems[v_i]);

    v_next_stage := v_stages[v_i];
    v_next_label := v_labels[v_i];

    IF v_row.enrollment_id IS NULL THEN
      IF v_i = 3 AND v_progression = 'retained_g11' AND NOT v_direct_g12 THEN
        v_blocked_reason := 'You have unresolved failing grades in Grade 11. Grade 12 enrollment is not available. Please contact the registrar.';
        v_next_stage := NULL;
      ELSIF v_i > v_start_i AND NOT is_stage_complete(v_student, v_grades[v_i - 1], v_sems[v_i - 1]) THEN
        v_blocked_reason := format(
          'Complete %s (enrollment, payment approval, and grades) before enrolling in %s.',
          v_labels[v_i - 1],
          v_labels[v_i]
        );
        v_next_stage := v_stages[v_i];
      END IF;
      EXIT;
    END IF;

    IF v_row.enrollment_status IN ('pending', 'approved') THEN
      v_blocked_reason := format(
        'Your %s enrollment is pending approval. Please wait for the administrator.',
        v_labels[v_i]
      );
      EXIT;
    END IF;

    IF v_row.enrollment_status = 'enrolled' AND COALESCE(v_row.payment_status, 'unpaid') <> 'approved' THEN
      v_blocked_reason := format(
        'Complete payment approval for %s before proceeding. Go to Payment / Accounts.',
        v_labels[v_i]
      );
      EXIT;
    END IF;

    IF v_row.enrollment_status = 'enrolled'
       AND COALESCE(v_row.payment_status, 'unpaid') = 'approved'
       AND COALESCE(v_row.graded_subjects, 0) < COALESCE(v_row.total_subjects, 0) THEN
      v_blocked_reason := format(
        'Your %s grades are not complete yet. Enrollment for the next term unlocks after grades are posted.',
        v_labels[v_i]
      );
      EXIT;
    END IF;

    IF v_row.enrollment_status = 'enrolled'
       AND COALESCE(v_row.failed_subjects, 0) > 0 THEN
      IF v_i <= 2 THEN
        v_blocked_reason := format(
          'You have failing grades in %s. Please contact the registrar before enrolling in the next term.',
          v_labels[v_i]
        );
      ELSE
        v_blocked_reason := format(
          'You have failing grades in %s. Please contact the registrar.',
          v_labels[v_i]
        );
      END IF;
      EXIT;
    END IF;

    EXIT;
  END LOOP;

  IF v_next_stage IS NULL AND COALESCE(array_length(v_completed, 1), 0) >= v_required_count THEN
    UPDATE students
    SET progression_status = 'graduated', updated_at = NOW()
    WHERE id = v_student AND progression_status <> 'graduated';

    RETURN json_build_object(
      'found', TRUE,
      'lifecycleStage', 'completed',
      'nextStage', NULL,
      'nextStageLabel', 'Grade 12 — 2nd Semester Completed',
      'completedStages', to_json(v_stages),
      'isCompleted', TRUE,
      'progressionStatus', 'graduated',
      'gradeLevel', v_grade_level
    );
  END IF;

  RETURN json_build_object(
    'found', TRUE,
    'lifecycleStage', COALESCE(v_next_stage, v_stages[4]),
    'nextStage', v_next_stage,
    'nextStageLabel', COALESCE(v_next_label, v_labels[4]),
    'completedStages', to_json(v_completed),
    'isCompleted', FALSE,
    'blockedReason', v_blocked_reason,
    'progressionStatus', v_progression,
    'gradeLevel', v_grade_level
  );
END;
$$;

CREATE OR REPLACE FUNCTION lifecycle_stage_matches_term(
  p_stage TEXT,
  p_grade_level TEXT,
  p_semester_code TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  RETURN (
    (p_stage = 'g11_1st' AND p_grade_level = 'Grade 11' AND p_semester_code = '1st')
    OR (p_stage = 'g11_2nd' AND p_grade_level = 'Grade 11' AND p_semester_code = '2nd')
    OR (p_stage = 'g12_1st' AND p_grade_level = 'Grade 12' AND p_semester_code = '1st')
    OR (p_stage = 'g12_2nd' AND p_grade_level = 'Grade 12' AND p_semester_code = '2nd')
  );
END;
$$;

-- ── Enrollment access with lifecycle enforcement ────────────

CREATE OR REPLACE FUNCTION get_student_enrollment_access(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_grade_level TEXT;
  v_account_status TEXT;
  v_progression TEXT;
  v_enrollment_open BOOLEAN;
  v_target_grade TEXT;
  v_current_status TEXT;
  v_semester_name TEXT;
  v_semester_code TEXT;
  v_can_enroll BOOLEAN := FALSE;
  v_reason TEXT := '';
  v_next_semester TEXT;
  v_lifecycle JSON;
  v_next_stage TEXT;
  v_is_completed BOOLEAN;
  v_blocked TEXT;
  v_stage_grade TEXT;
  v_stage_sem TEXT;
BEGIN
  SELECT s.id, s.grade_level, s.account_status, s.progression_status
  INTO v_student, v_grade_level, v_account_status, v_progression
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object('canEnroll', FALSE, 'reason', 'Student not found.');
  END IF;

  v_lifecycle := get_student_lifecycle_state(p_student_id);
  v_next_stage := v_lifecycle->>'nextStage';
  v_is_completed := COALESCE((v_lifecycle->>'isCompleted')::BOOLEAN, FALSE);
  v_blocked := v_lifecycle->>'blockedReason';

  SELECT sem.enrollment_open, sem.target_grade_level, sem.name, sem.code
  INTO v_enrollment_open, v_target_grade, v_semester_name, v_semester_code
  FROM semesters sem
  WHERE sem.is_current = TRUE
  LIMIT 1;

  v_next_semester := CASE
    WHEN COALESCE(v_semester_code, '1st') = '1st' THEN '2nd Semester'
    ELSE 'the next school year (1st Semester)'
  END;

  SELECT e.status INTO v_current_status
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id
  WHERE e.student_id = v_student AND sem.is_current = TRUE
  ORDER BY e.created_at DESC
  LIMIT 1;

  IF v_is_completed OR v_progression = 'graduated' THEN
    v_reason := 'You have completed the supported enrollment lifecycle (Grade 12 — 2nd Semester). No further enrollment is available.';
  ELSIF v_account_status = 'frozen' THEN
    v_reason := 'Your account has been frozen due to non-enrollment during the official registration period. Please contact the registrar''s office.';
  ELSIF v_account_status = 'inactive' THEN
    v_reason := 'Your account is inactive. Please contact the registrar''s office.';
  ELSIF NOT COALESCE(v_enrollment_open, FALSE) THEN
    v_reason := format(
      'Enrollment is currently closed for %s. Please wait for the registrar to open the registration period.',
      COALESCE(v_semester_name, 'this term')
    );
  ELSIF v_current_status IN ('pending', 'approved', 'enrolled') THEN
    v_reason := format(
      'You already have an enrollment submission for %s (%s). Please wait for the registrar to open %s before enrolling again.',
      COALESCE(v_semester_name, 'this term'),
      COALESCE(v_grade_level, 'your grade level'),
      v_next_semester
    );
  ELSIF v_blocked IS NOT NULL AND v_blocked <> '' THEN
    v_reason := v_blocked;
  ELSIF v_next_stage IS NULL THEN
    v_reason := 'Enrollment is not available for your current academic stage. Please contact the registrar.';
  ELSE
    v_stage_grade := CASE
      WHEN v_next_stage IN ('g11_1st', 'g11_2nd') THEN 'Grade 11'
      ELSE 'Grade 12'
    END;
    v_stage_sem := CASE
      WHEN v_next_stage IN ('g11_1st', 'g12_1st') THEN '1st'
      ELSE '2nd'
    END;

    IF NOT lifecycle_stage_matches_term(v_next_stage, v_stage_grade, v_stage_sem) THEN
      v_reason := format(
        'Your next enrollment stage is %s. The registrar must open that term before you can enroll.',
        v_lifecycle->>'nextStageLabel'
      );
    ELSIF v_target_grade IS NOT NULL AND v_target_grade <> v_stage_grade THEN
      v_reason := format(
        'Enrollment is open for %s only. Your next required stage is %s.',
        v_target_grade,
        v_lifecycle->>'nextStageLabel'
      );
    ELSIF COALESCE(v_semester_code, '1st') <> v_stage_sem THEN
      v_reason := format(
        'Enrollment is open for %s. Your next required stage is %s.',
        COALESCE(v_semester_name, 'this term'),
        v_lifecycle->>'nextStageLabel'
      );
    ELSIF v_progression = 'retained_g11' AND v_next_stage LIKE 'g12_%' THEN
      v_reason := 'You have unresolved failing grades in Grade 11. Grade 12 enrollment is not available until requirements are fulfilled. Please contact the registrar.';
    ELSIF v_target_grade IS NOT NULL
      AND v_target_grade <> v_stage_grade
      AND NOT (v_progression = 'eligible_g12' AND v_next_stage LIKE 'g12_%') THEN
      v_reason := format('Enrollment is open for %s only. Your next stage is %s.', v_target_grade, v_lifecycle->>'nextStageLabel');
    ELSE
      v_can_enroll := TRUE;
      v_reason := format('You may enroll for %s.', v_lifecycle->>'nextStageLabel');
    END IF;
  END IF;

  RETURN json_build_object(
    'canEnroll', v_can_enroll,
    'reason', v_reason,
    'enrollmentOpen', COALESCE(v_enrollment_open, FALSE),
    'accountStatus', v_account_status,
    'progressionStatus', v_progression,
    'gradeLevel', v_grade_level,
    'targetGradeLevel', v_target_grade,
    'currentEnrollmentStatus', v_current_status,
    'semesterName', v_semester_name,
    'semesterCode', v_semester_code,
    'nextSemesterLabel', v_next_semester,
    'lifecycleStage', v_lifecycle->>'lifecycleStage',
    'nextStage', v_lifecycle->>'nextStage',
    'nextStageLabel', v_lifecycle->>'nextStageLabel',
    'completedStages', v_lifecycle->'completedStages',
    'isLifecycleCompleted', v_is_completed
  );
END;
$$;

-- ── Progression after grade encoding ────────────────────────

CREATE OR REPLACE FUNCTION evaluate_student_progression(p_student_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_g11_2nd RECORD;
  v_g12_2nd RECORD;
  v_new_progression TEXT;
BEGIN
  IF is_stage_complete(p_student_id, 'Grade 11', '2nd') THEN
    SELECT * INTO v_g11_2nd FROM find_stage_enrollment(p_student_id, 'Grade 11', '2nd');

    IF COALESCE(v_g11_2nd.failed_subjects, 0) > 0 THEN
      v_new_progression := 'retained_g11';
      UPDATE students SET
        progression_status = v_new_progression,
        grade11_completed = FALSE,
        updated_at = NOW()
      WHERE id = p_student_id;
    ELSE
      v_new_progression := 'eligible_g12';
      UPDATE students SET
        progression_status = v_new_progression,
        grade_level = 'Grade 12',
        grade11_completed = TRUE,
        updated_at = NOW()
      WHERE id = p_student_id;
    END IF;

    RETURN json_build_object(
      'evaluated', TRUE,
      'scope', 'g11_2nd',
      'progressionStatus', v_new_progression,
      'failedCount', COALESCE(v_g11_2nd.failed_subjects, 0)
    );
  END IF;

  IF is_stage_complete(p_student_id, 'Grade 12', '2nd') THEN
    SELECT * INTO v_g12_2nd FROM find_stage_enrollment(p_student_id, 'Grade 12', '2nd');

    IF COALESCE(v_g12_2nd.failed_subjects, 0) = 0 THEN
      UPDATE students SET
        progression_status = 'graduated',
        updated_at = NOW()
      WHERE id = p_student_id;

      RETURN json_build_object(
        'evaluated', TRUE,
        'scope', 'g12_2nd',
        'progressionStatus', 'graduated',
        'failedCount', 0
      );
    END IF;

    RETURN json_build_object(
      'evaluated', TRUE,
      'scope', 'g12_2nd',
      'progressionStatus', 'in_progress',
      'failedCount', COALESCE(v_g12_2nd.failed_subjects, 0)
    );
  END IF;

  RETURN json_build_object('evaluated', FALSE, 'reason', 'Stage grades not yet complete');
END;
$$;

GRANT EXECUTE ON FUNCTION student_has_g11_history(UUID) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION find_stage_enrollment(UUID, TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION is_stage_complete(UUID, TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_student_lifecycle_state(TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION lifecycle_stage_matches_term(TEXT, TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_student_enrollment_access(TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION evaluate_student_progression(UUID) TO anon, authenticated, service_role;
