"""
ViolaWatch Web Server
Works on: Railway, Render, Fly.io, Heroku (all free tiers)
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, jsonify, request, send_from_directory, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading
from datetime import datetime

from database.db_manager import DatabaseManager
from core.detector import ViolationDetector
import config as cfg

app = Flask(__name__, 
            static_folder="web/static",
            template_folder="web/templates")
CORS(app)

app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_UPLOAD * 1024 * 1024
ALLOWED = {"mp4","avi","mov","mkv","wmv","webm"}

db = DatabaseManager()
detector = ViolationDetector(db=db)

ALLOWED_EXTENSIONS = lambda f: "." in f and f.rsplit(".",1)[1].lower() in ALLOWED


# ── PAGE ROUTES ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

@app.route("/<path:path>")
def static_files(path):
    full = os.path.join("web", path)
    if os.path.exists(full):
        return send_from_directory("web", path)
    return send_from_directory("web", "index.html")


# ── API: Stats ─────────────────────────────────────────────────────────────

@app.route("/api/stats")
def stats():
    s = db.get_stats()
    s["live"] = {
        "fps": detector.stats["fps"],
        "is_running": detector.is_running,
        "total": detector.stats["total"],
    }
    return jsonify(s)


# ── API: Violations ────────────────────────────────────────────────────────

@app.route("/api/violations")
def get_violations():
    page   = int(request.args.get("page",1))
    limit  = int(request.args.get("limit",25))
    vtype  = request.args.get("type")
    plate  = request.args.get("plate")
    offset = (page-1)*limit

    records = db.get_violations(limit=limit,offset=offset,
                                 violation_type=vtype,plate=plate)
    total   = db.count_violations(violation_type=vtype,plate=plate)

    # Serialize datetimes
    for r in records:
        for k,v in r.items():
            if hasattr(v,"isoformat"): r[k] = v.isoformat()

    return jsonify({"violations":records,"total":total,
                    "page":page,"pages":max(1,(total+limit-1)//limit)})


@app.route("/api/violations/<int:vid>")
def get_violation(vid):
    r = db.get_violation_by_id(vid)
    if not r: return jsonify({"error":"Not found"}),404
    for k,v in r.items():
        if hasattr(v,"isoformat"): r[k] = v.isoformat()
    return jsonify(r)


@app.route("/api/violations/<int:vid>/status", methods=["PATCH"])
def update_status(vid):
    data = request.json or {}
    db.update_violation(vid, data.get("status","pending"), data.get("notes"))
    return jsonify({"ok":True})


@app.route("/api/violations/<int:vid>", methods=["DELETE"])
def delete_violation(vid):
    db.delete_violation(vid)
    return jsonify({"ok":True})

@app.route("/api/violations/all", methods=["DELETE"])
def delete_all_violations():
    db.delete_all_violations()
    return jsonify({"ok":True})

@app.route("/api/violations/export")
def export_violations_csv():
    import csv, io
    records = db.get_violations(limit=100000)
    output = io.StringIO()
    if records:
        writer = csv.DictWriter(output, fieldnames=records[0].keys())
        writer.writeheader()
        for r in records:
            # Serialize datetime objects
            row = {k: (v.isoformat() if hasattr(v,"isoformat") else v) for k,v in r.items()}
            writer.writerow(row)
    output.seek(0)
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=violations.csv"}
    )


# ── API: Camera ────────────────────────────────────────────────────────────

@app.route("/api/camera/start", methods=["POST"])
def start_camera():
    data = request.json or {}
    src  = data.get("source",0)
    if isinstance(src,str) and src.isdigit(): src = int(src)
    try:
        if not detector.is_running:
            detector.start_live(src)
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500


@app.route("/api/camera/stop", methods=["POST"])
def stop_camera():
    detector.stop()
    return jsonify({"ok":True})


@app.route("/api/camera/frame")
def camera_frame():
    f = detector.get_frame_b64()
    return jsonify({"frame":f,"ok":bool(f)})


# ── API: Video Upload ──────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "file" not in request.files:
        return jsonify({"ok":False,"error":"No file"}),400
    f = request.files["file"]
    if not f.filename or not ALLOWED_EXTENSIONS(f.filename):
        return jsonify({"ok":False,"error":"Invalid file type"}),400

    fname = secure_filename(f.filename)
    os.makedirs(cfg.UPLOAD_DIR, exist_ok=True)
    path  = os.path.join(cfg.UPLOAD_DIR, fname)
    f.save(path)

    job_id = db.create_job(fname)
    detector.process_video_file(path, job_id)
    return jsonify({"ok":True,"job_id":job_id,"filename":fname})


@app.route("/api/jobs")
def get_jobs():
    jobs = db.get_all_jobs()
    for j in jobs:
        for k,v in j.items():
            if hasattr(v,"isoformat"): j[k] = v.isoformat()
    return jsonify({"jobs":jobs})


@app.route("/api/jobs/<int:jid>")
def get_job(jid):
    j = db.get_job(jid)
    if not j: return jsonify({"error":"Not found"}),404
    for k,v in j.items():
        if hasattr(v,"isoformat"): j[k] = v.isoformat()
    return jsonify(j)

@app.route("/api/jobs/<int:jid>", methods=["DELETE"])
def delete_job(jid):
    j = db.get_job(jid)
    if j:
        # Also delete the uploaded video file to free space
        video_path = os.path.join(cfg.UPLOAD_DIR, j.get("filename",""))
        if video_path and os.path.exists(video_path):
            try: os.remove(video_path)
            except Exception: pass
        db.delete_job(jid)
    return jsonify({"ok":True})


# ── API: Images ────────────────────────────────────────────────────────────

@app.route("/api/images/<path:filename>")
def serve_image(filename):
    import os
    # Security: only allow filenames, no path traversal
    safe = os.path.basename(filename)
    full = os.path.join(cfg.SNAPSHOT_DIR, safe)
    if not os.path.exists(full):
        return jsonify({"error":"Not found"}), 404
    return send_from_directory(cfg.SNAPSHOT_DIR, safe)


# ── API: Demo ──────────────────────────────────────────────────────────────

@app.route("/api/demo/seed")
def seed_demo():
    db.seed_demo()
    return jsonify({"ok":True})


# ── HEALTH CHECK (required by hosting platforms) ───────────────────────────

@app.route("/health")
@app.route("/api/health")
def health():
    return jsonify({"status":"ok","service":"violawatch","version":"2.0"})


if __name__ == "__main__":
    # Seed demo if empty
    s = db.get_stats()
    if s["total"] == 0:
        print("[Server] Seeding demo data...")
        db.seed_demo()

    print("="*55)
    print("  ViolaWatch Web Server")
    print(f"  Dashboard: http://localhost:{cfg.SERVER_PORT}")
    print("="*55)
    app.run(host=cfg.SERVER_HOST, port=cfg.SERVER_PORT,
            debug=False, threaded=True)
