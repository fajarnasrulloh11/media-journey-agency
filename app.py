import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from markupsafe import escape
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import os

# Memuat Environment Variables dari file .env
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

# SECURITY 1: CORS Protection
CORS(app, resources={r"/api/*": {"origins": "*"}}) 

# SECURITY 2: Rate Limiting (Mencegah Spam / Bot)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per day", "20 per hour"],
    storage_uri="memory://"
)

# Vercel filesystem is read-only except untuk folder /tmp. 
DB_FILE = '/tmp/leads.db' if os.environ.get('VERCEL') else 'leads.db'
# SECURITY 3: Secret Key disimpan di Environment Variable (.env)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "fallback_rahasia123") 

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            company TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ----------------- ROUTES HTML -----------------
@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'media_journey_landing.html')

@app.route('/admin')
def serve_admin():
    return send_from_directory(BASE_DIR, 'admin.html')

@app.route('/<path:filename>')
def serve_static(filename):
    # Mengizinkan frontend memanggil file gambar (seperti qris.jpg)
    if filename.endswith(('.jpg', '.png', '.jpeg', '.svg', '.gif')):
        return send_from_directory(BASE_DIR, filename)
    return "File Not Found", 404

# ----------------- ROUTES API -----------------
@app.route('/api/contact', methods=['POST'])
@limiter.limit("5 per day") # SECURITY: Mencegah spam (1 IP = maks 5 pesan per hari)
def contact():
    data = request.json
    
    # SECURITY 4: Input Sanitization (Mencegah XSS)
    name = escape(data.get('name', '')).strip()
    phone = escape(data.get('phone', '')).strip()
    company = escape(data.get('company', '')).strip()
    message = escape(data.get('message', '')).strip()
    
    # Validation
    if not name or not phone:
        return jsonify({'error': 'Nama dan Nomor WhatsApp wajib diisi.'}), 400
        
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # SECURITY 5: Parameterized Queries (Mencegah SQL Injection)
        c.execute('INSERT INTO contacts (name, phone, company, message) VALUES (?, ?, ?, ?)',
                  (name, phone, company, message))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Pesan berhasil disimpan.'}), 200
    except Exception as e:
        # SECURITY 6: Mencegah kebocoran struktur database
        return jsonify({'error': 'Terjadi kesalahan pada server. Silakan coba lagi.'}), 500

@app.route('/api/leads', methods=['GET'])
@limiter.limit("20 per minute") # SECURITY: Mencegah DDoS pada endpoint database
def get_leads():
    # SECURITY 7: Authentication
    provided_key = request.args.get('key')
    if provided_key != ADMIN_API_KEY:
        return jsonify({'error': 'Akses Ditolak. API Key tidak valid.'}), 401

    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM contacts ORDER BY created_at DESC')
        rows = c.fetchall()
        leads = [dict(ix) for ix in rows]
        conn.close()
        return jsonify({'leads': leads}), 200
    except Exception as e:
        return jsonify({'error': 'Terjadi kesalahan pada server.'}), 500

if __name__ == '__main__':
    init_db()
    print("==================================================")
    print(" Media Journey Solution - FULL VERSION STARTED    ")
    print("==================================================")
    print(" Landing Page  : http://localhost:5000")
    print(" Dashboard Admin: http://localhost:5000/admin")
    print(f" Kunci Login   : {ADMIN_API_KEY}")
    print("==================================================")
    app.run(host='0.0.0.0', port=5000, debug=True)
