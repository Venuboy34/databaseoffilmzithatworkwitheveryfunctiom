CREATE TABLE media (
  id SERIAL PRIMARY KEY,
  type VARCHAR(10) NOT NULL CHECK (type IN ('movie','tv')),
  title TEXT NOT NULL,
  description TEXT,
  thumbnail TEXT,
  backdrop TEXT,
  release_date DATE,
  language VARCHAR(10),
  rating NUMERIC(3,1),
  cast_members JSON,
  video_links JSON,
  download_links JSON,
  torrent_links JSON,
  total_seasons INT,
  seasons JSON,
  genres JSON,
  file_type VARCHAR(20) DEFAULT 'webrip'  -- Added file_type for both movies and TV series
);
