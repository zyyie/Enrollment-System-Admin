  -- Run once in Supabase SQL Editor.
  -- Creates a public bucket for admission document uploads (Form 138, etc.).

  INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
  VALUES (
    'admission-documents',
    'admission-documents',
    true,
    10485760,
    ARRAY[
      'image/jpeg',
      'image/png',
      'image/webp',
      'image/gif',
      'application/pdf'
    ]::text[]
  )
  ON CONFLICT (id) DO UPDATE
  SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

  DROP POLICY IF EXISTS "Public read admission documents" ON storage.objects;
  CREATE POLICY "Public read admission documents"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'admission-documents');
