-- Fix 2nd Semester enrollment: seed schedules for Wisdom/Compassion sections
-- and remove invalid enrollments that block students from enrolling again.
-- Run in Supabase SQL Editor (requires section-names.sql helpers).

-- ── 1. ensure_enrollment_schedules: seed BOTH section slots (A + B) ──
CREATE OR REPLACE FUNCTION ensure_enrollment_schedules(
  p_strand_id UUID,
  p_grade_level TEXT,
  p_semester_code TEXT DEFAULT NULL
)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_semester UUID;
  v_semester_code TEXT;
  v_section UUID;
  v_section_name TEXT;
  v_slot TEXT;
  v_schedule_label TEXT;
  v_day_of_week TEXT;
  v_start TIME;
  v_end TIME;
  v_inserted INT := 0;
  v_total INT := 0;
BEGIN
  IF p_strand_id IS NULL OR p_grade_level IS NULL THEN
    RETURN 0;
  END IF;

  SELECT id, code INTO v_semester, v_semester_code
  FROM semesters
  WHERE is_current = TRUE
  LIMIT 1;

  IF v_semester IS NULL THEN
    RETURN 0;
  END IF;

  v_semester_code := COALESCE(NULLIF(TRIM(p_semester_code), ''), v_semester_code, '1st');

  FOREACH v_slot IN ARRAY ARRAY['A', 'B']
  LOOP
    IF v_slot = 'A' THEN
      v_schedule_label := 'MW 9:00AM-10:30AM';
      v_day_of_week := 'MW';
      v_start := TIME '09:00:00';
      v_end := TIME '10:30:00';
    ELSE
      v_schedule_label := 'TTh 1:00PM-2:30PM';
      v_day_of_week := 'TTh';
      v_start := TIME '13:00:00';
      v_end := TIME '14:30:00';
    END IF;

    SELECT build_section_name(code, p_grade_level, v_slot)
    INTO v_section_name
    FROM strands
    WHERE id = p_strand_id;

    INSERT INTO sections (name, strand_id, grade_level)
    VALUES (v_section_name, p_strand_id, p_grade_level)
    ON CONFLICT (name, strand_id, grade_level) DO NOTHING;

    SELECT id INTO v_section
    FROM sections
    WHERE name = v_section_name
      AND strand_id = p_strand_id
      AND grade_level = p_grade_level
    LIMIT 1;

    IF v_section IS NULL THEN
      CONTINUE;
    END IF;

    INSERT INTO class_schedules (
      subject_id, section_id, semester_id, schedule_label, day_of_week,
      start_time, end_time, max_slots, is_active, is_published
    )
    SELECT sub.id, v_section, v_semester, v_schedule_label, v_day_of_week,
      v_start, v_end, 40, TRUE, TRUE
    FROM subjects sub
    WHERE sub.is_active = TRUE
      AND sub.grade_level = p_grade_level
      AND (sub.semester_code IS NULL OR sub.semester_code = v_semester_code)
      AND (sub.strand_id IS NULL OR sub.strand_id = p_strand_id)
      AND NOT EXISTS (
        SELECT 1
        FROM class_schedules cs
        WHERE cs.subject_id = sub.id
          AND cs.section_id = v_section
          AND cs.semester_id = v_semester
          AND COALESCE(cs.is_active, TRUE) = TRUE
      );

    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    v_total := v_total + v_inserted;
  END LOOP;

  RETURN v_total;
END;
$$;

-- ── 2. Ensure canonical sections exist for all strands ─────────────
INSERT INTO sections (name, strand_id, grade_level)
SELECT build_section_name(str.code, g.gl, slot.slot), str.id, g.gl
FROM strands str
CROSS JOIN (VALUES ('Grade 11'), ('Grade 12')) AS g(gl)
CROSS JOIN (VALUES ('A'), ('B')) AS slot(slot)
WHERE str.is_active = TRUE
ON CONFLICT (name, strand_id, grade_level) DO NOTHING;

-- ── 3. Seed missing schedules for current semester (both slots) ────
INSERT INTO class_schedules (
  subject_id, section_id, semester_id, schedule_label, day_of_week,
  start_time, end_time, max_slots, is_active, is_published
)
SELECT sub.id, sec.id, sem.id, 'MW 9:00AM-10:30AM', 'MW',
  TIME '09:00:00', TIME '10:30:00', 40, TRUE, TRUE
FROM subjects sub
JOIN sections sec ON sec.grade_level = sub.grade_level
  AND (sub.strand_id IS NULL OR sub.strand_id = sec.strand_id)
JOIN strands str ON str.id = sec.strand_id AND str.is_active = TRUE
JOIN semesters sem ON sem.is_current = TRUE
WHERE sub.is_active = TRUE
  AND sec.name = build_section_name(str.code, sub.grade_level, 'A')
  AND (sub.semester_code IS NULL OR sub.semester_code = sem.code)
  AND NOT EXISTS (
    SELECT 1 FROM class_schedules cs
    WHERE cs.subject_id = sub.id AND cs.section_id = sec.id AND cs.semester_id = sem.id
      AND COALESCE(cs.is_active, TRUE) = TRUE
  );

INSERT INTO class_schedules (
  subject_id, section_id, semester_id, schedule_label, day_of_week,
  start_time, end_time, max_slots, is_active, is_published
)
SELECT sub.id, sec.id, sem.id, 'TTh 1:00PM-2:30PM', 'TTh',
  TIME '13:00:00', TIME '14:30:00', 40, TRUE, TRUE
FROM subjects sub
JOIN sections sec ON sec.grade_level = sub.grade_level
  AND (sub.strand_id IS NULL OR sub.strand_id = sec.strand_id)
JOIN strands str ON str.id = sec.strand_id AND str.is_active = TRUE
JOIN semesters sem ON sem.is_current = TRUE
WHERE sub.is_active = TRUE
  AND sec.name = build_section_name(str.code, sub.grade_level, 'B')
  AND (sub.semester_code IS NULL OR sub.semester_code = sem.code)
  AND NOT EXISTS (
    SELECT 1 FROM class_schedules cs
    WHERE cs.subject_id = sub.id AND cs.section_id = sec.id AND cs.semester_id = sem.id
      AND COALESCE(cs.is_active, TRUE) = TRUE
  );

-- Deactivate legacy ICT 11-A / STEM 11-A style rows (letter-only suffix)
UPDATE class_schedules cs
SET is_active = FALSE
FROM sections sec
JOIN strands st ON st.id = sec.strand_id
WHERE cs.section_id = sec.id
  AND COALESCE(cs.is_active, TRUE) = TRUE
  AND TRIM(SPLIT_PART(sec.name, '-', 2)) NOT IN (
    section_slot_name(st.code, sec.grade_level, 'A'),
    section_slot_name(st.code, sec.grade_level, 'B')
  )
  AND TRIM(SPLIT_PART(sec.name, '-', 2)) ~ '^(A|B)$';

-- ── 4. Remove invalid 2nd-sem enrollments (1st-sem subjects) ───────
DO $$
DECLARE
  v_bad UUID[];
BEGIN
  SELECT ARRAY_AGG(DISTINCT e.id)
  INTO v_bad
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id
  JOIN enrollment_subjects es ON es.enrollment_id = e.id
  JOIN subjects sub ON sub.id = es.subject_id
  WHERE sem.is_current = TRUE
    AND sem.code = '2nd'
    AND sub.semester_code = '1st';

  IF v_bad IS NOT NULL AND array_length(v_bad, 1) > 0 THEN
    DELETE FROM enrollment_subjects WHERE enrollment_id = ANY(v_bad);
    DELETE FROM enrollments WHERE id = ANY(v_bad);
    RAISE NOTICE 'Removed % invalid 2nd-sem enrollment(s) with 1st-sem subjects', array_length(v_bad, 1);
  END IF;
END $$;

-- ── 5. Auto-heal schedules for every active strand ─────────────────
DO $$
DECLARE
  r RECORD;
  v_sem_code TEXT;
BEGIN
  SELECT code INTO v_sem_code FROM semesters WHERE is_current = TRUE LIMIT 1;
  FOR r IN
    SELECT id, 'Grade 11' AS gl FROM strands WHERE is_active = TRUE
    UNION ALL
    SELECT id, 'Grade 12' AS gl FROM strands WHERE is_active = TRUE
  LOOP
    PERFORM ensure_enrollment_schedules(r.id, r.gl, v_sem_code);
  END LOOP;
END $$;

GRANT EXECUTE ON FUNCTION ensure_enrollment_schedules TO anon, authenticated, service_role;
