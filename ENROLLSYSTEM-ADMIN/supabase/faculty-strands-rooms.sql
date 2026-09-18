-- Faculty strand assignments + ensure all strands + admin API permissions
-- Run in Supabase SQL Editor after schema.sql

CREATE TABLE IF NOT EXISTS faculty_strands (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  faculty_id UUID NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
  strand_id UUID NOT NULL REFERENCES strands(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (faculty_id, strand_id)
);

CREATE INDEX IF NOT EXISTS idx_faculty_strands_faculty ON faculty_strands(faculty_id);
CREATE INDEX IF NOT EXISTS idx_faculty_strands_strand ON faculty_strands(strand_id);

INSERT INTO strands (code, name, track) VALUES
  ('STEM', 'STEM - Science, Technology, Engineering, and Mathematics', 'Academic'),
  ('ABM', 'Accountancy, Business & Management', 'Academic'),
  ('HUMSS', 'Humanities & Social Sciences', 'Academic'),
  ('GAS', 'General Academic Strand', 'Academic'),
  ('ICT', 'Information and Communications Technology', 'TechPro'),
  ('COOKERY', 'Cookery', 'TechPro'),
  ('EIM', 'Electrical Installation and Maintenance', 'TechPro')
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  track = EXCLUDED.track,
  is_active = TRUE;

INSERT INTO rooms (name, capacity, room_type) VALUES
  ('NB101', 40, 'classroom'),
  ('NB102', 40, 'classroom'),
  ('NB103', 40, 'classroom'),
  ('NB104', 40, 'classroom'),
  ('NB105', 40, 'classroom'),
  ('NB106', 40, 'classroom'),
  ('NB107', 40, 'classroom'),
  ('NB108', 40, 'classroom'),
  ('NB201', 40, 'classroom'),
  ('NB202', 40, 'classroom'),
  ('NB203', 40, 'classroom'),
  ('NB204', 40, 'classroom'),
  ('LAB1', 30, 'laboratory'),
  ('LAB2', 30, 'laboratory'),
  ('LAB3', 30, 'laboratory')
ON CONFLICT (name) DO NOTHING;

-- Admin server uses service_role key — grant full access to management tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.strands TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.subjects TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.faculty TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.faculty_strands TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.rooms TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.students TO service_role;
