CREATE TABLE media (

  id SERIAL PRIMARY KEY,

  type VARCHAR(10) NOT NULL CHECK (type IN ('movie','tv')),

  title TEXT NOT NULL,

  description TEXT,

  thumbnail TEXT,

  release_date DATE,

  language VARCHAR(10),

  rating NUMERIC(3,1),

  cast_members JSON,

  video_links JSON,      -- This column will store the JSON object with 720p, 1080p, 2160p video links

  download_links JSON,   -- This column will store the JSON object with 720p, 1080p, 2160p download links

  total_seasons INT,

  seasons JSON,

  genres JSON

);





CREATE TABLE media (
  id SERIAL PRIMARY KEY,
  type VARCHAR(10) NOT NULL CHECK (type IN ('movie','tv')),
  title TEXT NOT NULL,
  description TEXT,
  thumbnail TEXT,
  release_date DATE,
  language VARCHAR(10),
  rating NUMERIC(3,1),
  cast_members JSON,
  video_links JSON,      -- This column will store the JSON object with 720p, 1080p, 2160p video links
  download_links JSON,   -- This column will store the JSON object with 720p, 1080p, 2160p download links
  torrent_links JSON,    -- This column will store the JSON object with 720p, 1080p, 2160p torrent links
  total_seasons INT,
  seasons JSON,
  genres JSON
);
