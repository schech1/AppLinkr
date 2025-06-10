from flask import request, redirect, render_template, send_file, session, flash, url_for, jsonify
import uuid
import qrcode
import io
import base64
from db import get_db
from db import DATABASE_PATH
from db import delete_qr_code_by_id
from utils import is_valid_url, process_metrics
from metrics import get_client_ip
import os
from functools import wraps

def setup_routes(app, SERVER_URL, PASSWORD):

    # Authentication decorator for admin functions only
    def require_authentication(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'authenticated' not in session:
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Authentication required'}), 401
                flash('You must be logged in to access this page.', 'danger')
                return redirect(url_for('login_page'))
            return f(*args, **kwargs)
        return decorated_function

    # Helper function to detect JSON requests
    def is_json_request():
        """Check if the request expects a JSON response."""
        return (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('Accept', '') or
            request.headers.get('Content-Type', '').startswith('application/json')
        )

    # ====================
    # PUBLIC ROUTES (No authentication required)
    # ====================

    @app.route('/redirect_standard')
    def redirect_standard():
        """Redirect to the standard URL content."""
        qr_code_id = request.args.get('qr_code_id')    
        user_agent = request.headers.get('User-Agent')
        process_metrics(qr_code_id, user_agent)

        # Retrieve the URL content from the database
        db = get_db()
        qr_code_data = db.execute('SELECT content FROM qr_codes WHERE id = ?', (qr_code_id,)).fetchone()

        if qr_code_data is None or not is_valid_url(qr_code_data[0]):
            return "Invalid or missing URL", 400

        return redirect(qr_code_data[0])

    @app.route('/show/<code_id>')
    def show(code_id):
        """Serve the generated QR code image."""
        db = get_db()
        qr_code_data = db.execute('SELECT qr_image FROM qr_codes WHERE id = ?', (code_id,)).fetchone()

        if qr_code_data is None:
            return "QR Code not found", 404

        buf = io.BytesIO(qr_code_data[0])
        return send_file(buf, mimetype='image/png')

    @app.route('/redirect/<qr_code_id>')
    def redirect_to_store(qr_code_id):
        """Redirect the user to the appropriate store based on their device."""
        db = get_db()
        
        # Fetch the app store and play store URLs from the database
        qr_code_data = db.execute('SELECT app_store_url, play_store_url FROM qr_codes WHERE id = ?', (qr_code_id,)).fetchone()

        if not qr_code_data:
            return "QR Code not found", 404

        app_store_url, play_store_url = qr_code_data

        # Get user agent and determine device type
        user_agent = request.headers.get('User-Agent')
        device = process_metrics(qr_code_id, user_agent)

        # Redirect based on device type
        if device == "android" and play_store_url:
            return redirect(play_store_url)
        elif device == "ios" and app_store_url:
            return redirect(app_store_url)
        else:
            return "Device not recognized or no URL provided", 400

    # ====================
    # AUTHENTICATION ROUTES
    # ====================

    @app.route('/login', methods=['GET', 'POST'])
    def login_page():
        """Login page for authentication."""
        if request.method == 'POST':
            password = request.form.get('password')
            if password == PASSWORD:
                session['authenticated'] = True
                # Redirect to where the user was trying to go, or index by default
                next_page = request.args.get('next', url_for('index'))
                return redirect(next_page)
            else:
                flash('Invalid password', 'danger')
                return render_template('login.html'), 403

        # Show login page
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        """Logout and clear session."""
        session.pop('authenticated', None)
        flash('You have been logged out.', 'info')
        return redirect(url_for('login_page'))

    # ====================
    # PROTECTED ROUTES (Require authentication)
    # ====================

    @app.route('/', methods=['GET'])
    @require_authentication
    def index():
        """Main QR code generator page using index.html."""
        return render_template('index.html')

    @app.route('/create', methods=['POST'])
    @require_authentication
    def create():
        """Generate a QR code with either custom URL content or app store links."""
        title = request.form['title']
        app_store_url = request.form.get('app_store_url')
        play_store_url = request.form.get('play_store_url')
        content = request.form.get('content')

        # Check if either content or app store URLs are provided
        if not content and not (app_store_url and play_store_url):
            error_msg = 'You must provide either a standard URL or both App Store and Play Store URLs.'
            if is_json_request():
                return jsonify({'success': False, 'message': error_msg}), 400
            flash(error_msg, 'danger')
            return render_template('index.html')

        # Check for invalid URL in the standard content
        if content and not is_valid_url(content):
            error_msg = 'Invalid URL provided for standard QR.'
            if is_json_request():
                return jsonify({'success': False, 'message': error_msg}), 400
            flash(error_msg, 'danger')
            return render_template('index.html')

        # Check for invalid URLs in the app store fields
        if not content:
            if not (is_valid_url(app_store_url) and is_valid_url(play_store_url)):
                error_msg = 'Invalid URLs for App Store or Play Store.'
                if is_json_request():
                    return jsonify({'success': False, 'message': error_msg}), 400
                flash(error_msg, 'danger')
                return render_template('index.html')

        # Create a database connection and cursor
        db = get_db()
        cursor = db.cursor()

        # Generate a new UUID for the QR code
        qr_code_id = str(uuid.uuid4())

        # Generate the appropriate QR code URL
        if content:  # If content for a standard QR code is provided
            qr_url = f"{SERVER_URL}/redirect_standard?qr_code_id={qr_code_id}"  # Redirect for standard QR
            cursor.execute('INSERT INTO qr_codes (id, title, content, app_store_url, play_store_url) VALUES (?, ?, ?, ?, ?)',
                        (qr_code_id, title, content, "", ""))  # App Store URLs are empty for standard QR codes
        else:  # For app store links
            qr_url = f"{SERVER_URL}/redirect/{qr_code_id}"
            cursor.execute('INSERT INTO qr_codes (id, title, content, app_store_url, play_store_url) VALUES (?, ?, ?, ?, ?)',
                        (qr_code_id, title, "", app_store_url, play_store_url))

        db.commit()

        # Generate the QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')

        # Save the QR code image
        img_buf = io.BytesIO()
        img.save(img_buf, 'PNG')
        img_buf.seek(0)

        # Update the database with the QR code image
        cursor.execute('UPDATE qr_codes SET qr_image = ? WHERE id = ?', (img_buf.getvalue(), qr_code_id))
        db.commit()

        # Generate QR code URL to show in the template
        qr_code_url = f"{SERVER_URL}{url_for('show', code_id=qr_code_id)}"
        
        # Check if this is a JSON request
        if is_json_request():
            return jsonify({
                'success': True,
                'qr_code_id': qr_code_id,
                'qr_code_url': qr_code_url,
                'redirect_url': qr_url,
                'title': title
            })
        
        # Return index.html with QR code data
        return render_template('index.html', qr_code_url=qr_code_url)

    @app.route('/admin')
    @require_authentication
    def admin_dashboard():
        """Admin dashboard using admin_dashboard.html."""
        return render_template('admin_dashboard.html')

    @app.route('/delete/<qr_code_id>', methods=['GET'])
    @require_authentication
    def delete_qr_code(qr_code_id):
        """Delete a QR code entry from the database."""
        delete_qr_code_by_id(qr_code_id)
        flash('QR code deleted successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    @app.route('/download_db', methods=['GET'])
    @require_authentication
    def download_db():
        if os.path.exists(DATABASE_PATH):
            return send_file(DATABASE_PATH, as_attachment=True)
        else:
            return "Database file not found.", 404

    # ====================
    # API ROUTES (Protected)
    # ====================

    @app.route('/api/stats')
    @require_authentication
    def api_stats():
        """Return comprehensive statistics as JSON for the admin dashboard."""
        try:
            db = get_db()
            print("API /api/stats called - fetching statistics...")
            
            # Basic counts
            total_codes = db.execute('SELECT COUNT(*) FROM qr_codes').fetchone()[0]
            total_scans = db.execute('SELECT COUNT(*) FROM qr_code_tracking').fetchone()[0]
            
            # Device type breakdown
            ios_scans = db.execute('SELECT COUNT(*) FROM qr_code_tracking WHERE device_type = ?', ('ios',)).fetchone()[0]
            android_scans = db.execute('SELECT COUNT(*) FROM qr_code_tracking WHERE device_type = ?', ('android',)).fetchone()[0]
            other_scans = db.execute('SELECT COUNT(*) FROM qr_code_tracking WHERE device_type NOT IN (?, ?)', ('ios', 'android')).fetchone()[0]
            
            # Recent activity (last 7 days)
            recent_scans = db.execute('''
                SELECT COUNT(*) FROM qr_code_tracking 
                WHERE access_time >= datetime('now', '-7 days')
            ''').fetchone()[0]
            
            # Top QR codes by scans
            top_qr_codes = db.execute('''
                SELECT qc.title, qc.id, COUNT(qct.id) as scan_count
                FROM qr_codes qc
                LEFT JOIN qr_code_tracking qct ON qc.id = qct.qr_code_id
                GROUP BY qc.id, qc.title
                ORDER BY scan_count DESC
                LIMIT 5
            ''').fetchall()
            
            # Daily activity for the last 30 days
            daily_activity = db.execute('''
                SELECT DATE(access_time) as date, COUNT(*) as scans
                FROM qr_code_tracking
                WHERE access_time >= datetime('now', '-30 days')
                GROUP BY DATE(access_time)
                ORDER BY date DESC
            ''').fetchall()
            
            # Browser breakdown
            browser_stats = db.execute('''
                SELECT browser, COUNT(*) as count
                FROM qr_code_tracking
                WHERE browser IS NOT NULL AND browser != ''
                GROUP BY browser
                ORDER BY count DESC
                LIMIT 10
            ''').fetchall()
            
            # OS breakdown
            os_stats = db.execute('''
                SELECT os, COUNT(*) as count
                FROM qr_code_tracking
                WHERE os IS NOT NULL AND os != ''
                GROUP BY os
                ORDER BY count DESC
                LIMIT 10
            ''').fetchall()
            
            # Geographic breakdown
            region_stats = db.execute('''
                SELECT region, COUNT(*) as count
                FROM qr_code_tracking
                WHERE region IS NOT NULL AND region != ''
                GROUP BY region
                ORDER BY count DESC
                LIMIT 10
            ''').fetchall()
            
            result = {
                'overview': {
                    'totalCodes': total_codes,
                    'totalScans': total_scans,
                    'recentScans': recent_scans,
                    'iosScans': ios_scans,
                    'androidScans': android_scans,
                    'otherScans': other_scans
                },
                'topQrCodes': [{'title': row[0], 'id': row[1], 'scans': row[2]} for row in top_qr_codes],
                'dailyActivity': [{'date': row[0], 'scans': row[1]} for row in daily_activity],
                'browserStats': [{'browser': row[0], 'count': row[1]} for row in browser_stats],
                'osStats': [{'os': row[0], 'count': row[1]} for row in os_stats],
                'regionStats': [{'region': row[0], 'count': row[1]} for row in region_stats]
            }
            
            print(f"API /api/stats returning data: {len(top_qr_codes)} QR codes, {total_scans} total scans")
            return jsonify(result)
            
        except Exception as e:
            print(f"Error in /api/stats: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500

    @app.route('/api/qr-codes')
    @require_authentication  
    def api_qr_codes():
        """Return detailed QR code data for the admin dashboard."""
        try:
            db = get_db()
            print("API /api/qr-codes called - fetching QR codes...")
            
            qr_codes = db.execute('''
                SELECT qc.id, qc.title, qc.content, qc.app_store_url, qc.play_store_url,
                    COUNT(qct.id) as total_scans,
                    MAX(qct.access_time) as last_scan,
                    SUM(CASE WHEN qct.device_type = 'ios' THEN 1 ELSE 0 END) as ios_scans,
                    SUM(CASE WHEN qct.device_type = 'android' THEN 1 ELSE 0 END) as android_scans
                FROM qr_codes qc
                LEFT JOIN qr_code_tracking qct ON qc.id = qct.qr_code_id
                GROUP BY qc.id, qc.title, qc.content, qc.app_store_url, qc.play_store_url
                ORDER BY total_scans DESC
            ''').fetchall()
            
            result = [{
                'id': row[0],
                'title': row[1],
                'content': row[2],
                'appStoreUrl': row[3],
                'playStoreUrl': row[4], 
                'totalScans': row[5] or 0,
                'lastScan': row[6],
                'iosScans': row[7] or 0,
                'androidScans': row[8] or 0,
                'qrImageUrl': f"{SERVER_URL}/show/{row[0]}"
            } for row in qr_codes]
            
            print(f"API /api/qr-codes returning {len(result)} QR codes")
            return jsonify(result)
            
        except Exception as e:
            print(f"Error in /api/qr-codes: {str(e)}")
            return jsonify({'error': 'Internal server error'}), 500

    @app.template_filter('b64encode')
    def b64encode_filter(data):
        """Encode binary data to Base64 for embedding in HTML."""
        if data:
            return base64.b64encode(data).decode('utf-8')
        return ''