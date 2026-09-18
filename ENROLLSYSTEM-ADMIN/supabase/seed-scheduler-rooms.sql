-- Scheduler infrastructure: rooms for OR-Tools (24 classrooms + specialized labs)
-- Run in Supabase SQL Editor (safe to re-run — ON CONFLICT DO UPDATE)
-- Also run section-names.sql to fix Cookery/ICT/EIM section names.

-- Expand room_type allowed values (existing DB only had classroom / laboratory)
ALTER TABLE rooms DROP CONSTRAINT IF EXISTS rooms_room_type_check;
ALTER TABLE rooms ADD CONSTRAINT rooms_room_type_check
  CHECK (room_type IN (
    'classroom',
    'laboratory',
    'computer_lab',
    'science_lab',
    'cookery_lab',
    'eim_lab'
  ));

INSERT INTO rooms (name, capacity, room_type, is_active) VALUES
  ('NB101', 40, 'classroom', TRUE),
  ('NB102', 40, 'classroom', TRUE),
  ('NB103', 40, 'classroom', TRUE),
  ('NB104', 40, 'classroom', TRUE),
  ('NB105', 40, 'classroom', TRUE),
  ('NB106', 40, 'classroom', TRUE),
  ('NB107', 40, 'classroom', TRUE),
  ('NB108', 40, 'classroom', TRUE),
  ('NB109', 40, 'classroom', TRUE),
  ('NB110', 40, 'classroom', TRUE),
  ('NB111', 40, 'classroom', TRUE),
  ('NB112', 40, 'classroom', TRUE),
  ('NB113', 40, 'classroom', TRUE),
  ('NB114', 40, 'classroom', TRUE),
  ('NB115', 40, 'classroom', TRUE),
  ('NB116', 40, 'classroom', TRUE),
  ('NB117', 40, 'classroom', TRUE),
  ('NB118', 40, 'classroom', TRUE),
  ('NB119', 40, 'classroom', TRUE),
  ('NB120', 40, 'classroom', TRUE),
  ('NB121', 40, 'classroom', TRUE),
  ('NB122', 40, 'classroom', TRUE),
  ('NB123', 40, 'classroom', TRUE),
  ('NB124', 40, 'classroom', TRUE)
ON CONFLICT (name) DO UPDATE SET
  capacity = EXCLUDED.capacity,
  room_type = EXCLUDED.room_type,
  is_active = TRUE;

-- ── 3. Specialized labs (shared across strands / time slots) ────────────────
INSERT INTO rooms (name, capacity, room_type, is_active) VALUES
  ('LAB1', 40, 'computer_lab', TRUE),
  ('LAB2', 40, 'computer_lab', TRUE),
  ('LAB3', 40, 'science_lab', TRUE),
  ('LAB4', 40, 'science_lab', TRUE),
  ('COOKERY-LAB1', 40, 'cookery_lab', TRUE),
  ('COOKERY-LAB2', 40, 'cookery_lab', TRUE),
  ('EIM-LAB1', 40, 'eim_lab', TRUE),
  ('EIM-LAB2', 40, 'eim_lab', TRUE)
ON CONFLICT (name) DO UPDATE SET
  capacity = EXCLUDED.capacity,
  room_type = EXCLUDED.room_type,
  is_active = TRUE;

-- ── 4. Verify ───────────────────────────────────────────────────────────────
SELECT room_type, COUNT(*) AS room_count
FROM rooms
WHERE is_active = TRUE
GROUP BY room_type
ORDER BY room_type;
