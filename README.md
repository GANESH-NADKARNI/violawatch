# 🚦 ViolaWatch v2 — Traffic Violation Detection System

Real-time detection of **no-helmet motorcyclists** and **seatbelt violations**,  
with **license plate recognition**, MySQL storage, Desktop GUI, and web dashboard.

---

## 🤗 Hosted Model

[![Hugging Face Model](https://img.shields.io/badge/🤗%20Model-helmet--detection--yolov8-FFD21E?style=for-the-badge)](https://huggingface.co/Ganesh-Nadkarni/helmet-detection-yolov8)
[![Hugging Face Space](https://img.shields.io/badge/🤗%20Space-Helmet--Detection--Demo-FFD21E?style=for-the-badge)](https://huggingface.co/spaces/Ganesh-Nadkarni/Helmet-Detection-Demo)

The custom-trained YOLOv8 helmet-detection model referenced in the accuracy upgrade section below is published on Hugging Face, with a live demo Space to try it without any local setup.

---

## Quick Start

### Desktop GUI (Recommended for local use)
```bash
pip install -r requirements.txt
python main.py
```

### Web Server (Local or hosted)
```bash
pip install -r requirements.txt
python main.py --web
# Open http://localhost:5000
```

---

## MySQL Setup

### Option A: Local MySQL
```sql
CREATE DATABASE violawatch;
CREATE USER 'viola'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL ON violawatch.* TO 'viola'@'localhost';
```

Edit `config/config.ini`:
```ini
[database]
host = localhost
user = viola
password = your_password
database = violawatch
```

> **No MySQL?** The app auto-falls back to SQLite — just run it!

### Option B: Free MySQL cloud (for hosting)
- **PlanetScale** — free 5GB MySQL (https://planetscale.com)
- **Railway MySQL** — free tier (https://railway.app)
- **Aiven** — free 5GB (https://aiven.io)

Set environment variables instead of config.ini:
```
DB_HOST=...  DB_USER=...  DB_PASSWORD=...  DB_NAME=violawatch
```

---

## Free Hosting Deployment

### 🚂 Railway (Easiest — recommended)
1. Push code to GitHub
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Add MySQL plugin → copy connection vars to environment
4. It auto-detects `Procfile` and deploys

### 🎨 Render
1. Push to GitHub
2. https://render.com → New Web Service → connect repo
3. Render reads `render.yaml` automatically
4. Add MySQL env vars from Aiven/PlanetScale

### 🐳 Docker (anywhere)
```bash
docker build -t violawatch .
docker run -p 5000:5000 \
  -e DB_HOST=... -e DB_USER=... -e DB_PASSWORD=... \
  violawatch
```

### ☁️ Fly.io
```bash
fly launch --name violawatch
fly secrets set DB_HOST=... DB_USER=... DB_PASSWORD=...
fly deploy
```

---

## Video Upload (Testing)

From the web dashboard or Desktop GUI:
1. Click **Upload Video File**
2. Select MP4/AVI/MOV file (up to 500MB)
3. Processing runs in background — live preview updates in real-time
4. Violations auto-saved to database with snapshots

Supported formats: `mp4 avi mov mkv wmv webm`

---

## Camera Sources

| Type | Value |
|------|-------|
| Webcam | `0` |
| 2nd webcam | `1` |
| CCTV RTSP | `rtsp://user:pass@192.168.1.100:554/stream` |
| IP Camera | `http://192.168.1.101/video` |
| Video file | `/path/to/video.mp4` |

---

## Detection Accuracy

| Violation | Method | Expected Accuracy |
|-----------|--------|------------------|
| No Helmet | Skin-color head analysis | 75–85%* |
| No Seatbelt | Diagonal line detection | 70–80%* |
| License Plate | Contour + EasyOCR | 75–90% |

*Upgrade to custom-trained YOLOv8 model for 90-95%+ accuracy — already done, see [helmet-detection-yolov8](https://huggingface.co/Ganesh-Nadkarni/helmet-detection-yolov8) above:
```python
# Download free datasets from: https://universe.roboflow.com
# Then in config/config.ini:
[models]
helmet_model = models/helmet_yolov8m.pt
seatbelt_model = models/seatbelt_yolov8m.pt
```

---

## Project Structure
```
violawatch/
├── main.py              ← Entry point (GUI or web)
├── server.py            ← Flask web API
├── Procfile             ← Railway/Heroku deploy
├── Dockerfile            ← Docker deploy
├── render.yaml          ← Render deploy
├── railway.toml         ← Railway config
├── requirements.txt
├── config/
│   ├── config.ini       ← All settings
│   └── __init__.py      ← Config loader
├── core/
│   └── detector.py      ← Detection engine
├── utils/
│   ├── frame_processor.py  ← YOLOv8 pipeline
│   └── plate_reader.py     ← OCR
├── database/
│   └── db_manager.py    ← MySQL + SQLite
├── gui/
│   └── app.py           ← Desktop GUI (Tkinter)
└── web/
    └── index.html       ← Web dashboard
```

---

## Environment Variables (for hosting)

| Variable | Description |
|----------|-------------|
| `DB_HOST` | MySQL host |
| `DB_PORT` | MySQL port (default 3306) |
| `DB_USER` | MySQL username |
| `DB_PASSWORD` | MySQL password |
| `DB_NAME` | Database name |
| `PORT` | Server port (auto-set by hosting) |
