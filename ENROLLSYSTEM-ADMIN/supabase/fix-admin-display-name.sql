-- UI shows "Admin" via admin.js; optional DB cleanup for seeded registrar row
UPDATE admins
SET last_name = 'Admin', first_name = 'System', middle_name = '', updated_at = NOW()
WHERE admin_id = 'FAC-2026-0001';
