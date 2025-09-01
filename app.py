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

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        cast = []
        for member in data['credits']['cast'][:10]:
            cast.append({
                "name": member.get("name"),
                "character": member.get("character"),
                "image": f"https://image.tmdb.org/t/p/original{member.get('profile_path')}" if member.get('profile_path') else None
            })
        
        processed_data = {
            'title': data.get('title') if media_type == 'movie' else data.get('name'),
            'description': data.get('overview'),
            'thumbnail': f"https://image.tmdb.org/t/p/original{data.get('poster_path')}" if data.get('poster_path') else None,
            'release_date': data.get('release_date') if media_type == 'movie' else data.get('first_air_date'),
            'language': data.get('original_language'),
            'rating': data.get('vote_average'),
            'cast_members': cast,
            'total_seasons': data.get('number_of_seasons') if media_type == 'tv' else None,
            'genres': [g['name'] for g in data.get('genres', [])] # Extract genres
        }
        
        return processed_data
    return None

def fetch_genres(media_type):
    url = f"https://api.themoviedb.org/3/genre/{media_type}/list?api_key={TMDB_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get('genres', [])
    return []

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

# --- Public API Endpoints ---
@app.route("/api/media", methods=["GET"])
def get_all_media():
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM media ORDER BY id DESC;")
    media = cur.fetchall()
    return jsonify([dict(row) for row in media])

@app.route("/api/media/<int:media_id>", methods=["GET"])
def get_single_media(media_id):
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM media WHERE id = %s;", (media_id,))
    media = cur.fetchone()
    if media:
        return jsonify(dict(media))
    return jsonify({"message": "Media not found"}), 404

@app.route("/api/genres", methods=["GET"])
def get_all_genres():
    movie_genres = fetch_genres('movie')
    tv_genres = fetch_genres('tv')
    # Combine and deduplicate genres
    all_genres = {genre['name'] for genre in movie_genres}
    all_genres.update({genre['name'] for genre in tv_genres})
    return jsonify(sorted(list(all_genres)))

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
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO media (type, title, description, thumbnail, release_date, language, rating, cast_members, video_links, download_links, total_seasons, seasons, genres)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            data.get('type'), data.get('title'), data.get('description'), data.get('thumbnail'),
            data.get('release_date'), data.get('language'), data.get('rating'),
            json.dumps(data.get('cast_members')), json.dumps(data.get('video_links')), json.dumps(data.get('download_links')),
            data.get('total_seasons'), json.dumps(data.get('seasons')), json.dumps(data.get('genres')) # Added genres here
        ))
        media_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"message": "Media added successfully", "id": media_id}), 201
    except (psycopg2.DatabaseError, json.JSONDecodeError) as e:
        conn.rollback()
        return jsonify({"message": "Error adding media", "error": str(e)}), 400

@app.route("/api/admin/media/<int:media_id>", methods=["PUT"])
@requires_auth
def update_media(media_id):
    data = request.json
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE media SET
                type = %s, title = %s, description = %s, thumbnail = %s, release_date = %s,
                language = %s, rating = %s, cast_members = %s, video_links = %s, download_links = %s,
                total_seasons = %s, seasons = %s, genres = %s
            WHERE id = %s;
        """, (
            data.get('type'), data.get('title'), data.get('description'), data.get('thumbnail'),
            data.get('release_date'), data.get('language'), data.get('rating'),
            json.dumps(data.get('cast_members')), json.dumps(data.get('video_links')), json.dumps(data.get('download_links')),
            data.get('total_seasons'), json.dumps(data.get('seasons')), json.dumps(data.get('genres')), media_id # Added genres here
        ))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"message": "Media not found"}), 404
        return jsonify({"message": "Media updated successfully"}), 200
    except (psycopg2.DatabaseError, json.JSONDecodeError) as e:
        conn.rollback()
        return jsonify({"message": "Error updating media", "error": str(e)}), 400

@app.route("/api/admin/media/<int:media_id>", methods=["DELETE"])
@requires_auth
def delete_media(media_id):
    conn, error = get_db()
    if error:
        return jsonify({"message": "Database connection error", "error": error}), 500
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM media WHERE id = %s;", (media_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"message": "Media not found"}), 404
        return jsonify({"message": "Media deleted successfully"}), 200
    except psycopg2.DatabaseError as e:
        conn.rollback()
        return jsonify({"message": "Error deleting media", "error": str(e)}), 400

if __name__ == "__main__":
    # For production, set host='0.0.0.0' to allow external connections
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
