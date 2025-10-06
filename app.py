import os
import requests
import json
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, render_template, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from base64 import b64decode
from flask_cors import CORS

app = Flask(__name__)

# Enable CORS for all routes to allow cross-origin requests from websites and apps
CORS(app)

# --- Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL') or "postgresql://<user>:<password>@<host>:<port>/<dbname>"
TMDB_API_KEY = "52f6a75a38a397d940959b336801e1c3"
ADMIN_USERNAME = "venura"
ADMIN_PASSWORD_HASH = generate_password_hash("venura")

# --- Database Connection ---
def get_db():
    if 'db' not in g:
        try:
            # Set sslmode='require' for secure connection to Neon Tech
            g.db = psycopg2.connect(DATABASE_URL, sslmode='require')
        except psycopg2.Error as e:
            return None, str(e)
    return g.db, None

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- Basic Authentication ---
def check_auth(username, password):
    return username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password)

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'message': 'Authorization Required'}), 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
        try:
            auth_type, credentials = auth_header.split()
            if auth_type.lower() == 'basic':
                decoded_credentials = b64decode(credentials).decode('utf-8')
                username, password = decoded_credentials.split(':', 1)
                if check_auth(username, password):
                    return f(*args, **kwargs)
        except Exception:
            pass
        return jsonify({'message': 'Authorization Failed'}), 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
    return decorated

# --- TMDB API Helper ---
def fetch_tmdb_data(tmdb_id, media_type):
    url = ""
    if media_type == 'movie':
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
    elif media_type == 'tv':
        url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=credits"
    
    if not url:
        return None

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            cast = []
            for member in data['credits']['cast'][:10]:
                cast.append({
                    "name": member.get("name"),
                    "character": member.get("character"),
                    "image": f"https://image.tmdb.org/t/p/original{member.get('profile_path')}" if member.get('profile_path') else None
                })
            
            # Initialize empty video links for both movie and TV
            video_links = {
                '720p': "",  # Empty placeholder for 720p
                '1080p': "",  # Empty placeholder for 1080p
                '2160p': ""   # Empty placeholder for 2160p
            }

            processed_data = {
                'title': data.get('title') if media_type == 'movie' else data.get('name'),
                'description': data.get('overview'),
                'thumbnail': f"https://image.tmdb.org/t/p/original{data.get('poster_path')}" if data.get('poster_path') else None,
                'release_date': data.get('release_date') if media_type == 'movie' else data.get('first_air_date'),
                'language': data.get('original_language'),
                'rating': data.get('vote_average'),
                'cast_members': cast,
                'total_seasons': data.get('number_of_seasons') if media_type == 'tv' else None,
                'genres': [g['name'] for g in data.get('genres', [])],
                'video_links': video_links  # Now includes 720p, 1080p and 2160p placeholders
            }
            
            return processed_data
        else:
            return None
    except requests.RequestException:
        return None

def fetch_genres(media_type):
    url = f"https://api.themoviedb.org/3/genre/{media_type}/list?api_key={TMDB_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get('genres', [])
        return []
    except requests.RequestException:
        return []

# --- Helper Functions ---
def safe_json_loads(data, default=None):
    """Safely parse JSON data with proper error handling"""
    if data is None:
        return default
    if isinstance(data, (dict, list)):
        return data
    try:
        return json.loads(data) if data else default
    except (json.JSONDecodeError, TypeError):
        return default

def clean_value(value):
    """Clean and validate input values"""
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return value

def prepare_media_data(data):
    """Prepare and validate media data before database operations"""
    print("Raw data received:", data)  # Debug log
    
    # Process genres - handle both string and array input
    genres = data.get('genres', [])
    if isinstance(genres, str):
        genres = [g.strip() for g in genres.split(',')] if genres else []
    elif genres is None:
        genres = []
    
    # Process video links
    video_links = {}
    if data.get('video_links'):
        video_links = safe_json_loads(data.get('video_links'), {})
    else:
        # Handle individual video link fields
        video_links = {
            '720p': clean_value(data.get('video_720p')),
            '1080p': clean_value(data.get('video_1080p')),
            '2160p': clean_value(data.get('video_2160p'))
        }
    
    # Process download links
    download_links = {}
    if data.get('download_links'):
        download_links = safe_json_loads(data.get('download_links'), {})
    else:
        # Handle individual download link fields
        download_720p = clean_value(data.get('download_720p'))
        download_1080p = clean_value(data.get('download_1080p'))
        download_2160p = clean_value(data.get('download_2160p'))
        
        if download_720p:
            download_links['720p'] = {'url': download_720p, 'file_type': 'webrip'}
        if download_1080p:
            download_links['1080p'] = {'url': download_1080p, 'file_type': 'webrip'}
        if download_2160p:
            download_links['2160p'] = {'url': download_2160p, 'file_type': 'webrip'}
    
    # Process torrent links
    torrent_links = {}
    if data.get('torrent_links'):
        torrent_links = safe_json_loads(data.get('torrent_links'), {})
    else:
        # Handle individual torrent link fields
        torrent_links = {
            '720p': clean_value(data.get('torrent_720p')),
            '1080p': clean_value(data.get('torrent_1080p')),
            '2160p': clean_value(data.get('torrent_2160p'))
        }
    
    # Handle rating - allow empty/null
    rating = data.get('rating')
    if rating in [None, '']:
        rating = None
    else:
        try:
            rating = float(rating)
        except (ValueError, TypeError):
            rating = None
    
    # Handle total_seasons for TV series
    total_seasons = data.get('total_seasons')
    if total_seasons in [None, '']:
        total_seasons = None
    else:
        try:
            total_seasons = int(total_seasons)
        except (ValueError, TypeError):
            total_seasons = None
    
    prepared_data = {
        'type': data.get('type'),
        'title': clean_value(data.get('title', '')),
        'description': clean_value(data.get('description')),
        'thumbnail': clean_value(data.get('thumbnail')),
        'release_date': clean_value(data.get('release_date')),
        'language': clean_value(data.get('language')),
        'rating': rating,
        'cast_members': safe_json_loads(data.get('cast_members'), []),
        'video_links': video_links,
        'download_links': download_links,
        'torrent_links': torrent_links,
        'total_seasons': total_seasons,
        'seasons': safe_json_loads(data.get('seasons')),
        'genres': genres
    }
    
    print("Prepared data:", prepared_data)  # Debug log
    return prepared_data

# --- Main Public Routes ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/docs")
def api_docs():
    return render_template("api_docs.html")

# --- Admin Panel Routes (HTML/JS) ---
@app.route("/admin")
@requires_auth
def admin_dashboard():
    return render_template("admin_dashboard.html")

@app.route("/admin/add_movie")
@requires_auth
def add_movie_page():
    return render_template("add_movie.html")

@app.route("/admin/add_tv")
@requires_auth
def add_tv_page():
    return render_template("add_tv.html")

@app.route("/admin/search_and_edit")
@requires_auth
def search_and_edit_page():
    return render_template("search_and_edit.html")

@app.route("/admin/edit")
@requires_auth
def edit_media_page():
    return render_template("edit_media.html")

@app.route("/admin/add_episode")
@requires_auth
def add_episode_page():
    media_id = request.args.get('media_id')
    if not media_id:
        return "Media ID required", 400
    
    conn, error = get_db()
    if error:
        return f"Database error: {error}", 500
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, title FROM media WHERE id = %s AND type = 'tv';", (media_id,))
    media = cur.fetchone()
    
    if not media:
        return "TV series not found", 404
    
    return render_template("add_episode.html", media=dict(media))

# --- Public API Endpoints ---
@app.route("/api/media", methods=["GET"])
def get_all_media():
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM media ORDER BY id DESC;")
        media = cur.fetchall()
        
        # Parse JSON fields for proper frontend consumption
        media_list = []
        for row in media:
            media_dict = dict(row)
            # Parse JSON fields
            media_dict['cast_members'] = safe_json_loads(media_dict.get('cast_members'), [])
            media_dict['video_links'] = safe_json_loads(media_dict.get('video_links'), {})
            media_dict['download_links'] = safe_json_loads(media_dict.get('download_links'), {})
            media_dict['torrent_links'] = safe_json_loads(media_dict.get('torrent_links'), {})
            media_dict['seasons'] = safe_json_loads(media_dict.get('seasons'))
            media_dict['genres'] = safe_json_loads(media_dict.get('genres'), [])
            media_list.append(media_dict)
        
        return jsonify(media_list)
    except psycopg2.Error as e:
        return jsonify({"message": "Database error", "error": str(e)}), 500

@app.route("/api/media/<int:media_id>", methods=["GET"])
def get_single_media(media_id):
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM media WHERE id = %s;", (media_id,))
        media = cur.fetchone()
        
        if media:
            media_dict = dict(media)
            # Parse JSON fields for frontend
            media_dict['cast_members'] = safe_json_loads(media_dict.get('cast_members'), [])
            media_dict['video_links'] = safe_json_loads(media_dict.get('video_links'), {})
            media_dict['download_links'] = safe_json_loads(media_dict.get('download_links'), {})
            media_dict['torrent_links'] = safe_json_loads(media_dict.get('torrent_links'), {})
            media_dict['seasons'] = safe_json_loads(media_dict.get('seasons'))
            media_dict['genres'] = safe_json_loads(media_dict.get('genres'), [])
            return jsonify(media_dict)
        
        return jsonify({"message": "Media not found"}), 404
    except psycopg2.Error as e:
        return jsonify({"message": "Database error", "error": str(e)}), 500

@app.route("/api/genres", methods=["GET"])
def get_all_genres():
    try:
        movie_genres = fetch_genres('movie')
        tv_genres = fetch_genres('tv')
        # Combine and deduplicate genres
        all_genres = {genre['name'] for genre in movie_genres}
        all_genres.update({genre['name'] for genre in tv_genres})
        return jsonify(sorted(list(all_genres)))
    except Exception as e:
        return jsonify({"message": "Error fetching genres", "error": str(e)}), 500

# --- Admin API Endpoints ---
@app.route("/api/admin/tmdb_fetch", methods=["POST"])
@requires_auth
def tmdb_fetch_api():
    data = request.json
    tmdb_id = data.get("tmdb_id")
    media_type = data.get("media_type")
    
    if not tmdb_id or not media_type:
        return jsonify({"message": "TMDB ID and media type are required"}), 400
    
    tmdb_data = fetch_tmdb_data(tmdb_id, media_type)
    if tmdb_data:
        return jsonify(tmdb_data), 200
    
    return jsonify({"message": "Failed to fetch data from TMDB"}), 404

@app.route("/api/admin/media", methods=["POST"])
@requires_auth
def add_media():
    data = request.json
    print("Received data for new media:", data)  # Debug log
    
    if not data or not data.get('title'):
        return jsonify({"message": "Title is required"}), 400
    
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    
    try:
        media_data = prepare_media_data(data)
        
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO media (type, title, description, thumbnail, release_date, language, rating, 
                              cast_members, video_links, download_links, torrent_links,
                              total_seasons, seasons, genres)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            media_data['type'], 
            media_data['title'], 
            media_data['description'], 
            media_data['thumbnail'],
            media_data['release_date'], 
            media_data['language'], 
            media_data['rating'],
            json.dumps(media_data['cast_members']), 
            json.dumps(media_data['video_links']), 
            json.dumps(media_data['download_links']),
            json.dumps(media_data['torrent_links']),
            media_data['total_seasons'], 
            json.dumps(media_data['seasons']), 
            json.dumps(media_data['genres'])
        ))
        
        media_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"message": "Media added successfully", "id": media_id}), 201
        
    except (psycopg2.DatabaseError, json.JSONDecodeError, ValueError) as e:
        conn.rollback()
        print("Error adding media:", str(e))  # Debug log
        return jsonify({"message": "Error adding media", "error": str(e)}), 400

@app.route("/api/admin/media/<int:media_id>", methods=["PUT"])
@requires_auth
def update_media(media_id):
    data = request.json
    print(f"Received update data for media {media_id}:", data)  # Debug log
    
    if not data or not data.get('title'):
        return jsonify({"message": "Title is required"}), 400
    
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    
    try:
        media_data = prepare_media_data(data)
        
        cur = conn.cursor()
        cur.execute("""
            UPDATE media SET
                type = %s, title = %s, description = %s, thumbnail = %s, release_date = %s,
                language = %s, rating = %s, cast_members = %s, video_links = %s, 
                download_links = %s, torrent_links = %s, total_seasons = %s, seasons = %s, genres = %s
            WHERE id = %s;
        """, (
            media_data['type'], 
            media_data['title'], 
            media_data['description'], 
            media_data['thumbnail'],
            media_data['release_date'], 
            media_data['language'], 
            media_data['rating'],
            json.dumps(media_data['cast_members']), 
            json.dumps(media_data['video_links']), 
            json.dumps(media_data['download_links']),
            json.dumps(media_data['torrent_links']),
            media_data['total_seasons'], 
            json.dumps(media_data['seasons']), 
            json.dumps(media_data['genres']),
            media_id
        ))
        
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"message": "Media not found"}), 404
        
        print(f"Media {media_id} updated successfully")  # Debug log
        return jsonify({"message": "Media updated successfully"}), 200
        
    except (psycopg2.DatabaseError, json.JSONDecodeError, ValueError) as e:
        conn.rollback()
        print("Error updating media:", str(e))  # Debug log
        return jsonify({"message": "Error updating media", "error": str(e)}), 400

@app.route("/api/admin/media/<int:media_id>/episode", methods=["POST"])
@requires_auth
def add_episode(media_id):
    data = request.json
    if not data:
        return jsonify({"message": "Episode data is required"}), 400
    
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    
    try:
        # Get current media data
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT seasons FROM media WHERE id = %s AND type = 'tv';", (media_id,))
        media = cur.fetchone()
        
        if not media:
            return jsonify({"message": "TV series not found"}), 404
        
        current_seasons = safe_json_loads(media['seasons'], {})
        
        # Prepare episode data
        season_number = data.get('season_number')
        episode_data = {
            'episode_number': data.get('episode_number'),
            'episode_name': data.get('episode_name'),
            'video_720p': data.get('video_links', {}).get('720p'),
            'video_1080p': data.get('video_links', {}).get('1080p'),
            'video_2160p': data.get('video_links', {}).get('2160p'),
            'download_720p': data.get('download_links', {}).get('720p'),
            'download_1080p': data.get('download_links', {}).get('1080p'),
            'download_2160p': data.get('download_links', {}).get('2160p'),
            'torrent_720p': data.get('torrent_links', {}).get('720p'),
            'torrent_1080p': data.get('torrent_links', {}).get('1080p'),
            'torrent_2160p': data.get('torrent_links', {}).get('2160p')
        }
        
        # Add episode to season
        season_key = f'season_{season_number}'
        if season_key not in current_seasons:
            current_seasons[season_key] = {
                'season_number': season_number,
                'total_episodes': 0,
                'episodes': []
            }
        
        # Add episode
        current_seasons[season_key]['episodes'].append(episode_data)
        current_seasons[season_key]['total_episodes'] = len(current_seasons[season_key]['episodes'])
        
        # Update database
        cur.execute("""
            UPDATE media SET seasons = %s 
            WHERE id = %s;
        """, (json.dumps(current_seasons), media_id))
        
        conn.commit()
        return jsonify({"message": "Episode added successfully"}), 200
        
    except (psycopg2.DatabaseError, json.JSONDecodeError, ValueError) as e:
        conn.rollback()
        return jsonify({"message": "Error adding episode", "error": str(e)}), 400

@app.route("/api/admin/media/<int:media_id>", methods=["DELETE"])
@requires_auth
def delete_media(media_id):
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM media WHERE id = %s;", (media_id,))
        conn.commit()
        
        if cur.rowcount == 0:
            return jsonify({"message": "Media not found"}), 404
        
        return jsonify({"message": "Media deleted successfully"}), 200
        
    except psycopg2.DatabaseError as e:
        conn.rollback()
        return jsonify({"message": "Error deleting media", "error": str(e)}), 400

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"message": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"message": "Internal server error"}), 500

if __name__ == "__main__":
    # For production, set host='0.0.0.0' to allow external connections
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)  # Set debug=True for development
