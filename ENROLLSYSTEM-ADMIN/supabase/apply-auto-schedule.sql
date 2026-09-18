-- Persist AI / auto-generated class schedules into Supabase
-- Run after schema.sql

CREATE OR REPLACE FUNCTION apply_generated_schedules(p_payload JSON)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_grade_level TEXT;
  v_semester_code TEXT;
  v_semester UUID;
  v_item JSON;
  v_session JSON;
  v_strand UUID;
  v_subject UUID;
  v_section UUID;
  v_room UUID;
  v_schedule UUID;
  v_section_name TEXT;
  v_grade_num TEXT;
  v_day TEXT;
  v_label TEXT;
  v_count INT := 0;
BEGIN
  v_grade_level := COALESCE(p_payload->>'gradeLevel', 'Grade 12');
  v_semester_code := COALESCE(p_payload->>'semesterCode', '1st');
  v_grade_num := CASE WHEN v_grade_level LIKE '%11%' THEN '11' ELSE '12' END;

  SELECT id INTO v_semester
  FROM semesters
  WHERE is_current = TRUE
  LIMIT 1;

  IF v_semester IS NULL THEN
    RAISE EXCEPTION 'No active semester configured';
  END IF;

  FOR v_item IN SELECT * FROM json_array_elements(COALESCE(p_payload->'schedules', '[]'::json))
  LOOP
    SELECT id INTO v_strand FROM strands WHERE code = UPPER(v_item->>'strand') LIMIT 1;
    IF v_strand IS NULL THEN
      RAISE EXCEPTION 'Unknown strand: %', v_item->>'strand';
    END IF;

    v_section_name := build_section_name(v_item->>'strand', v_grade_level, v_item->>'section');

    INSERT INTO sections (name, strand_id, grade_level)
    VALUES (v_section_name, v_strand, v_grade_level)
    ON CONFLICT DO NOTHING;

    SELECT id INTO v_section FROM sections WHERE name = v_section_name LIMIT 1;

    SELECT id INTO v_subject FROM subjects WHERE code = v_item->>'subject_code' LIMIT 1;
    IF v_subject IS NULL THEN
      INSERT INTO subjects (code, name, strand_id, grade_level, semester_code, lec_hours, lab_hours, units)
      VALUES (
        v_item->>'subject_code',
        COALESCE(v_item->>'subject_name', v_item->>'subject_code'),
        CASE WHEN v_item->>'strand' IS NULL THEN NULL ELSE v_strand END,
        v_grade_level,
        v_semester_code,
        3, 0, 3
      )
      ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
      RETURNING id INTO v_subject;
    END IF;

    v_label := COALESCE(v_item->>'schedule_label', 'TBA');
    v_day := 'MW';

    IF json_array_length(COALESCE(v_item->'sessions', '[]'::json)) > 0 THEN
      SELECT string_agg(DISTINCT s->>'day', ', ' ORDER BY s->>'day')
      INTO v_day
      FROM json_array_elements(v_item->'sessions') s;
    END IF;

    SELECT id INTO v_room
    FROM rooms
    WHERE UPPER(name) = UPPER((v_item->'sessions'->0->>'room'))
    LIMIT 1;

    IF v_room IS NULL AND json_array_length(COALESCE(v_item->'sessions', '[]'::json)) > 0 THEN
      INSERT INTO rooms (name, capacity, room_type)
      VALUES (UPPER(v_item->'sessions'->0->>'room'), 40, 'classroom')
      ON CONFLICT (name) DO NOTHING
      RETURNING id INTO v_room;
      IF v_room IS NULL THEN
        SELECT id INTO v_room FROM rooms WHERE UPPER(name) = UPPER(v_item->'sessions'->0->>'room') LIMIT 1;
      END IF;
    END IF;

    DELETE FROM class_schedules
    WHERE subject_id = v_subject
      AND section_id = v_section
      AND semester_id = v_semester;

    INSERT INTO class_schedules (
      subject_id,
      section_id,
      semester_id,
      room_id,
      day_of_week,
      schedule_label,
      max_slots
    )
    VALUES (
      v_subject,
      v_section,
      v_semester,
      v_room,
      COALESCE(v_day, 'MW'),
      v_label,
      40
    )
    RETURNING id INTO v_schedule;

    v_count := v_count + 1;
  END LOOP;

  RETURN json_build_object(
    'success', TRUE,
    'applied', v_count,
    'semesterId', v_semester,
    'gradeLevel', v_grade_level,
    'semesterCode', v_semester_code
  );
END;
$$;

GRANT EXECUTE ON FUNCTION apply_generated_schedules TO anon, authenticated;
