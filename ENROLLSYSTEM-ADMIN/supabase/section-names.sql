-- Named sections per strand/grade (replaces Section A/B labels)
-- Run ONCE in Supabase SQL Editor after schema.sql

CREATE OR REPLACE FUNCTION section_slot_name(
  p_strand_code TEXT,
  p_grade_level TEXT,
  p_slot TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v_code TEXT := UPPER(TRIM(COALESCE(p_strand_code, 'STEM')));
  v_slot TEXT := UPPER(TRIM(COALESCE(p_slot, 'A')));
  v_grade11 BOOLEAN := COALESCE(p_grade_level, '') LIKE '%11%';
BEGIN
  IF v_grade11 THEN
    RETURN CASE v_code
      WHEN 'STEM' THEN CASE WHEN v_slot = 'A' THEN 'Hope' ELSE 'Fortitude' END
      WHEN 'ABM' THEN CASE WHEN v_slot = 'A' THEN 'Faith' ELSE 'Integrity' END
      WHEN 'HUMSS' THEN CASE WHEN v_slot = 'A' THEN 'Perseverance' ELSE 'Courage' END
      WHEN 'COOKERY' THEN CASE WHEN v_slot = 'A' THEN 'Wisdom' ELSE 'Compassion' END
      WHEN 'EIM' THEN CASE WHEN v_slot = 'A' THEN 'Resilience' ELSE 'Justice' END
      WHEN 'ICT' THEN CASE WHEN v_slot = 'A' THEN 'Humility' ELSE 'Kindness' END
      ELSE v_slot
    END;
  END IF;

  RETURN CASE v_code
    WHEN 'STEM' THEN CASE WHEN v_slot = 'A' THEN 'Rizal' ELSE 'Bonifacio' END
    WHEN 'ABM' THEN CASE WHEN v_slot = 'A' THEN 'Aguinaldo' ELSE 'Mabini' END
    WHEN 'HUMSS' THEN CASE WHEN v_slot = 'A' THEN 'Luna' ELSE 'Jacinto' END
    WHEN 'COOKERY' THEN CASE WHEN v_slot = 'A' THEN 'Del Pilar' ELSE 'Silang' END
    WHEN 'EIM' THEN CASE WHEN v_slot = 'A' THEN 'Aquino' ELSE 'Malvar' END
    WHEN 'ICT' THEN CASE WHEN v_slot = 'A' THEN 'Zamora' ELSE 'Gomez' END
    ELSE v_slot
  END;
END;
$$;

CREATE OR REPLACE FUNCTION build_section_name(
  p_strand_code TEXT,
  p_grade_level TEXT,
  p_section_key TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v_code TEXT := UPPER(TRIM(COALESCE(p_strand_code, 'STEM')));
  v_grade_num TEXT := CASE WHEN COALESCE(p_grade_level, '') LIKE '%11%' THEN '11' ELSE '12' END;
  v_key TEXT := TRIM(COALESCE(p_section_key, 'A'));
  v_key_upper TEXT := UPPER(v_key);
  v_name TEXT;
BEGIN
  IF v_key ~ '^\s*\w+\s+\d{2}-' THEN
    RETURN v_key;
  END IF;

  IF v_key_upper IN ('A', 'B') THEN
    v_name := section_slot_name(v_code, p_grade_level, v_key_upper);
  ELSIF UPPER(TRIM(v_key)) = UPPER(section_slot_name(v_code, p_grade_level, 'A')) THEN
    v_name := section_slot_name(v_code, p_grade_level, 'A');
  ELSIF UPPER(TRIM(v_key)) = UPPER(section_slot_name(v_code, p_grade_level, 'B')) THEN
    v_name := section_slot_name(v_code, p_grade_level, 'B');
  ELSE
    RAISE EXCEPTION 'Invalid section % for strand % (%) — use A or B only.',
      v_key, v_code, p_grade_level;
  END IF;

  RETURN v_code || ' ' || v_grade_num || '-' || v_name;
END;
$$;

-- Rename legacy Section A/B rows
UPDATE sections sec
SET name = build_section_name(
  str.code,
  sec.grade_level,
  CASE
    WHEN sec.name ~ '-A$' THEN 'A'
    WHEN sec.name ~ '-B$' THEN 'B'
    ELSE sec.name
  END
)
FROM strands str
WHERE str.id = sec.strand_id
  AND (sec.name ~ '-A$' OR sec.name ~ '-B$');

GRANT EXECUTE ON FUNCTION section_slot_name TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION build_section_name TO anon, authenticated, service_role;
