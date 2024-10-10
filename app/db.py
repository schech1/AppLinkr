import sqlite3
from flask import g
from db import DATABASE_PATH



DATABASE_FOLDER = "db"
DATABASE_PATH = f"{DATABASE_FOLDER}/database.db"

def get_db():
    """Get a database connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH)

        # Create qr_codes table with qr_image allowing NULL values
        g.db.execute('''CREATE TABLE IF NOT EXISTS qr_codes
                        (id TEXT PRIMARY KEY,
                         title TEXT NOT NULL,
                         content TEXT,                     
                         app_store_url TEXT NOT NULL,
                         play_store_url TEXT NOT NULL,
                         qr_image BLOB)''')

        g.db.execute('''CREATE TABLE IF NOT EXISTS qr_code_tracking
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         qr_code_id TEXT NOT NULL,
                         device_type TEXT NOT NULL,
                         ip_address TEXT NOT NULL,
                         access_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                         region TEXT,
                         browser TEXT,
                         os TEXT,
                         language TEXT,
                         referrer TEXT,
                         FOREIGN KEY (qr_code_id) REFERENCES qr_codes(id))''')
    return g.db

def close_db(exception):
    """Close the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def delete_qr_code_by_id(qr_code_id):
    """Delete a QR code by its ID."""
    db = get_db()
    db.execute('DELETE FROM qr_codes WHERE id = ?', (qr_code_id,))
    db.execute('DELETE FROM qr_code_tracking WHERE qr_code_id = ?', (qr_code_id,))
    db.commit()
