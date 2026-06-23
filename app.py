import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for

app = Flask(__name__)

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'qac_data.db'))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS mills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT,
            mill_type TEXT,
            contact_person TEXT,
            contact_phone TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mill_id INTEGER,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            department TEXT,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(mill_id) REFERENCES mills(id)
        );
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mill_id INTEGER,
            project_id INTEGER,
            department TEXT,
            filename TEXT,
            original_path TEXT,
            stored_path TEXT,
            version INTEGER DEFAULT 1,
            uploaded_at TEXT DEFAULT (datetime('now','localtime')),
            uploaded_by TEXT DEFAULT 'QAC Team',
            notes TEXT,
            FOREIGN KEY(mill_id) REFERENCES mills(id)
        );
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mill_id INTEGER,
            action TEXT,
            details TEXT,
            done_by TEXT DEFAULT 'QAC Team',
            done_at TEXT DEFAULT (datetime('now','localtime'))
        );
    ''')
    conn.commit()
    conn.close()

def log_activity(mill_id, action, details):
    conn = get_db()
    conn.execute("INSERT INTO activity_log (mill_id, action, details) VALUES (?,?,?)",
                 (mill_id, action, details))
    conn.commit()
    conn.close()

@app.route('/')
def dashboard():
    conn = get_db()
    mills = conn.execute("SELECT * FROM mills ORDER BY name").fetchall()
    total_mills = conn.execute("SELECT COUNT(*) FROM mills").fetchone()[0]
    total_projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM projects WHERE status='Pending'").fetchone()[0]
    files_month = conn.execute(
        "SELECT COUNT(*) FROM files WHERE strftime('%Y-%m', uploaded_at)=strftime('%Y-%m','now','localtime')"
    ).fetchone()[0]
    recent_activity = conn.execute(
        "SELECT a.*, m.name as mill_name FROM activity_log a LEFT JOIN mills m ON a.mill_id=m.id ORDER BY a.done_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return render_template('dashboard.html', mills=mills, total_mills=total_mills,
                           total_projects=total_projects, pending=pending,
                           files_month=files_month, recent_activity=recent_activity)

@app.route('/mills')
def mills_list():
    q = request.args.get('q', '')
    conn = get_db()
    if q:
        mills = conn.execute("SELECT * FROM mills WHERE name LIKE ? OR location LIKE ? OR mill_type LIKE ? ORDER BY name",
                             (f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
    else:
        mills = conn.execute("SELECT * FROM mills ORDER BY name").fetchall()
    mills_data = []
    for m in mills:
        file_count = conn.execute("SELECT COUNT(*) FROM files WHERE mill_id=?", (m['id'],)).fetchone()[0]
        proj_count = conn.execute("SELECT COUNT(*) FROM projects WHERE mill_id=?", (m['id'],)).fetchone()[0]
        mills_data.append({'mill': m, 'file_count': file_count, 'proj_count': proj_count})
    conn.close()
    return render_template('mills.html', mills_data=mills_data, q=q)

@app.route('/mill/add', methods=['GET', 'POST'])
def add_mill():
    if request.method == 'POST':
        name = request.form['name']
        conn = get_db()
        conn.execute("INSERT INTO mills (name, location, mill_type, contact_person, contact_phone, notes) VALUES (?,?,?,?,?,?)",
                     (name, request.form.get('location'), request.form.get('mill_type'),
                      request.form.get('contact_person'), request.form.get('contact_phone'),
                      request.form.get('notes')))
        conn.commit()
        mid = conn.execute("SELECT id FROM mills WHERE name=? ORDER BY id DESC", (name,)).fetchone()[0]
        log_activity(mid, 'Mill Added', f'New mill: {name}')
        conn.close()
        return redirect(url_for('mill_detail', mill_id=mid))
    return render_template('add_mill.html')

@app.route('/mill/<int:mill_id>')
def mill_detail(mill_id):
    conn = get_db()
    mill = conn.execute("SELECT * FROM mills WHERE id=?", (mill_id,)).fetchone()
    if not mill:
        return redirect(url_for('mills_list'))
    files_tech = conn.execute("SELECT * FROM files WHERE mill_id=? AND department='Technical' ORDER BY uploaded_at DESC", (mill_id,)).fetchall()
    files_draw = conn.execute("SELECT * FROM files WHERE mill_id=? AND department='Drawings' ORDER BY uploaded_at DESC", (mill_id,)).fetchall()
    files_prod = conn.execute("SELECT * FROM files WHERE mill_id=? AND department='Production' ORDER BY uploaded_at DESC", (mill_id,)).fetchall()
    projects = conn.execute("SELECT * FROM projects WHERE mill_id=? ORDER BY created_at DESC", (mill_id,)).fetchall()
    activity = conn.execute("SELECT * FROM activity_log WHERE mill_id=? ORDER BY done_at DESC LIMIT 20", (mill_id,)).fetchall()
    conn.close()
    return render_template('mill_detail.html', mill=mill, files_tech=files_tech,
                           files_draw=files_draw, files_prod=files_prod,
                           projects=projects, activity=activity)

@app.route('/mill/<int:mill_id>/edit', methods=['GET', 'POST'])
def edit_mill(mill_id):
    conn = get_db()
    mill = conn.execute("SELECT * FROM mills WHERE id=?", (mill_id,)).fetchone()
    if request.method == 'POST':
        conn.execute("UPDATE mills SET name=?, location=?, mill_type=?, contact_person=?, contact_phone=?, notes=? WHERE id=?",
                     (request.form['name'], request.form.get('location'), request.form.get('mill_type'),
                      request.form.get('contact_person'), request.form.get('contact_phone'),
                      request.form.get('notes'), mill_id))
        conn.commit()
        log_activity(mill_id, 'Mill Updated', 'Mill info updated')
        conn.close()
        return redirect(url_for('mill_detail', mill_id=mill_id))
    conn.close()
    return render_template('add_mill.html', mill=mill, edit=True)

@app.route('/mill/<int:mill_id>/delete', methods=['POST'])
def delete_mill(mill_id):
    conn = get_db()
    conn.execute("DELETE FROM files WHERE mill_id=?", (mill_id,))
    conn.execute("DELETE FROM projects WHERE mill_id=?", (mill_id,))
    conn.execute("DELETE FROM activity_log WHERE mill_id=?", (mill_id,))
    conn.execute("DELETE FROM mills WHERE id=?", (mill_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('mills_list'))

@app.route('/mill/<int:mill_id>/upload', methods=['POST'])
def upload_file(mill_id):
    dept = request.form.get('department', 'Technical')
    notes = request.form.get('notes', '')
    folder = os.path.join(os.path.dirname(__file__), 'uploads', str(mill_id), dept)
    os.makedirs(folder, exist_ok=True)
    files = request.files.getlist('files')
    conn = get_db()
    for f in files:
        if f.filename:
            fname = f.filename
            base, ext = os.path.splitext(fname)
            existing = conn.execute(
                "SELECT MAX(version) FROM files WHERE mill_id=? AND department=? AND filename=?",
                (mill_id, dept, fname)).fetchone()[0]
            version = (existing or 0) + 1
            stored_name = f"{base}_v{version}{ext}" if version > 1 else fname
            stored_path = os.path.join(folder, stored_name)
            f.save(stored_path)
            conn.execute(
                "INSERT INTO files (mill_id, department, filename, stored_path, version, notes) VALUES (?,?,?,?,?,?)",
                (mill_id, dept, fname, stored_path, version, notes))
            log_activity(mill_id, 'File Uploaded', f'{dept}: {fname} (v{version})')
    conn.commit()
    conn.close()
    return redirect(url_for('mill_detail', mill_id=mill_id))

@app.route('/file/download/<int:file_id>')
def download_file(file_id):
    conn = get_db()
    f = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    conn.close()
    if f and os.path.exists(f['stored_path']):
        return send_file(f['stored_path'], as_attachment=True, download_name=f['filename'])
    return "File not found", 404

@app.route('/file/delete/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    conn = get_db()
    f = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if f:
        if os.path.exists(f['stored_path']):
            os.remove(f['stored_path'])
        mill_id = f['mill_id']
        conn.execute("DELETE FROM files WHERE id=?", (file_id,))
        log_activity(mill_id, 'File Deleted', f"Deleted: {f['filename']}")
        conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/mill/<int:mill_id>/project/add', methods=['POST'])
def add_project(mill_id):
    conn = get_db()
    conn.execute("INSERT INTO projects (mill_id, title, status, department, description) VALUES (?,?,?,?,?)",
                 (mill_id, request.form['title'], request.form.get('status', 'Pending'),
                  request.form.get('department'), request.form.get('description')))
    conn.commit()
    log_activity(mill_id, 'Project Added', f"New project: {request.form['title']}")
    conn.close()
    return redirect(url_for('mill_detail', mill_id=mill_id))

@app.route('/project/update/<int:proj_id>', methods=['POST'])
def update_project(proj_id):
    conn = get_db()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (proj_id,)).fetchone()
    if proj:
        new_status = request.form.get('status', proj['status'])
        conn.execute("UPDATE projects SET status=? WHERE id=?", (new_status, proj_id))
        log_activity(proj['mill_id'], 'Project Updated', f"Status -> {new_status}: {proj['title']}")
        conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/project/delete/<int:proj_id>', methods=['POST'])
def delete_project(proj_id):
    conn = get_db()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (proj_id,)).fetchone()
    if proj:
        conn.execute("DELETE FROM projects WHERE id=?", (proj_id,))
        log_activity(proj['mill_id'], 'Project Deleted', f"Deleted: {proj['title']}")
        conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/activity')
def activity_log():
    conn = get_db()
    logs = conn.execute(
        "SELECT a.*, m.name as mill_name FROM activity_log a LEFT JOIN mills m ON a.mill_id=m.id ORDER BY a.done_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return render_template('activity.html', logs=logs)

@app.route('/search')
def search():
    q = request.args.get('q', '')
    conn = get_db()
    mills = conn.execute("SELECT * FROM mills WHERE name LIKE ? OR location LIKE ?",
                         (f'%{q}%', f'%{q}%')).fetchall() if q else []
    files = conn.execute(
        "SELECT f.*, m.name as mill_name FROM files f JOIN mills m ON f.mill_id=m.id WHERE f.filename LIKE ? ORDER BY f.uploaded_at DESC",
        (f'%{q}%',)).fetchall() if q else []
    conn.close()
    return render_template('search.html', q=q, mills=mills, files=files)

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=False)
