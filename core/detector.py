"""ViolaWatch — Core Violation Detector Engine with Auto-Verification"""
import cv2, os, time, threading, base64, uuid
import numpy as np
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.frame_processor import FrameProcessor
import config as cfg


class ViolationDetector:
    def __init__(self, db=None, on_violation=None):
        self.db           = db
        self.on_violation = on_violation
        self.processor    = FrameProcessor(cfg.CONFIDENCE)
        self.is_running   = False
        self.cap          = None
        self._lock        = threading.Lock()
        self._current_frame = None
        self._seen: dict  = {}
        self.GRID         = 120
        self.COOLDOWN     = max(cfg.COOLDOWN, 30)  # minimum 30s between same-zone saves
        self.stats        = {"fps":0,"total":0,"helmet":0,"seatbelt":0,"frames":0}

        # ── Auto-verification buffer ──────────────────────────────────────
        # key = (gx, gy, vtype)
        # value = { "hits": int, "first_frame": int, "last_v": dict,
        #           "last_frame": np.ndarray, "committed": bool }
        # A violation must appear in VERIFY_HITS consecutive
        # detection passes within VERIFY_WINDOW frames to be committed.
        self._verify_buf: dict = {}
        self.VERIFY_HITS   = 5    # must be detected 5 times before committing
        self.VERIFY_WINDOW = 60   # within 60 processed frames (~6 seconds)

    # ── LIVE CAMERA ───────────────────────────────────────────────────────

    def start_live(self, source=0):
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open source: {source}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.is_running = True
        t = threading.Thread(target=self._live_loop, daemon=True)
        t.start()
        print(f"[Detector] Live started: {source}")

    def stop(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None

    def _live_loop(self):
        fc, fps_t, fps_cnt = 0, time.time(), 0
        proc_frame = 0  # processed frame counter for verification window
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05); continue
            fc += 1; fps_cnt += 1
            if time.time()-fps_t >= 1.0:
                self.stats["fps"] = fps_cnt; fps_cnt=0; fps_t=time.time()
            if fc % cfg.FRAME_SKIP != 0: continue
            proc_frame += 1
            self.stats["frames"] += 1
            annotated, violations = self.processor.process(frame)
            self._draw_hud(annotated)

            # Mark which zones are currently active violations
            active_keys = set()
            for v in violations:
                key = self._vkey(v)
                active_keys.add(key)
                self._auto_verify(frame, v, key, proc_frame, source_type="live")

            # Draw CONFIRMING overlay for zones still accumulating hits
            for key, buf in list(self._verify_buf.items()):
                if buf["committed"]: continue
                if key not in active_keys: continue
                if buf["hits"] < self.VERIFY_HITS:
                    bx1,by1,bx2,by2 = buf["last_v"].get("bbox",(0,0,50,50))
                    # Yellow pulsing box = confirming
                    cv2.rectangle(annotated,(bx1,by1),(bx2,by2),(0,220,255),2)
                    progress = int((buf["hits"] / self.VERIFY_HITS) * 100)
                    self._put_verify_label(annotated,
                        f"VERIFYING {progress}%", (bx1,by1))

            # Expire stale verification buffers
            self._verify_buf = {
                k:b for k,b in self._verify_buf.items()
                if proc_frame - b["first_frame"] < self.VERIFY_WINDOW * 2
                and not (b["committed"] and
                         proc_frame - b["first_frame"] > self.VERIFY_WINDOW)
            }

            with self._lock:
                self._current_frame = annotated.copy()

    # ── VIDEO FILE ────────────────────────────────────────────────────────

    def process_video_file(self, path, job_id=None, progress_cb=None, done_cb=None):
        t = threading.Thread(
            target=self._video_file_loop,
            args=(path, job_id, progress_cb, done_cb), daemon=True)
        t.start()

    def _video_file_loop(self, path, job_id, progress_cb, done_cb):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            if done_cb: done_cb(0, "Cannot open video")
            return
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps    = cap.get(cv2.CAP_PROP_FPS) or 25
        f_cool = int(fps * max(cfg.COOLDOWN, 15))
        if self.db and job_id:
            self.db.update_job(job_id, status="processing", total_frames=total)

        frame_seen: dict = {}
        self._seen       = {}
        self._verify_buf = {}
        violations_count = 0
        fc   = 0
        proc = 0
        skip = max(cfg.FRAME_SKIP, 5)

        while True:
            ret, frame = cap.read()
            if not ret: break
            fc += 1
            if fc % skip != 0: continue
            proc += 1
            annotated, violations = self.processor.process(frame)
            with self._lock:
                self._current_frame = annotated.copy()

            for v in violations:
                key = self._vkey(v)
                if fc - frame_seen.get(key, -f_cool-1) < f_cool:
                    continue
                # For video: require 2 hits in 20 frames before committing
                buf = self._verify_buf.setdefault(key, {
                    "hits":0,"first_frame":proc,"committed":False,
                    "last_v":v,"last_frame":frame.copy()
                })
                if buf["committed"]: continue
                if proc - buf["first_frame"] > 20:
                    # Reset window
                    buf.update({"hits":0,"first_frame":proc})
                buf["hits"]       += 1
                buf["last_v"]      = v
                buf["last_frame"]  = frame.copy()
                if buf["hits"] >= 2:
                    buf["committed"] = True
                    frame_seen[key]  = fc
                    self._save_violation(buf["last_frame"], v, source_type="video")
                    violations_count += 1

            if progress_cb and fc%(skip*10)==0:
                progress_cb(int((fc/max(total,1))*100), fc, violations_count)
            if self.db and job_id and fc%(skip*30)==0:
                self.db.update_job(job_id, processed=fc, violations_found=violations_count)

        cap.release()
        if self.db and job_id:
            self.db.update_job(job_id, status="done", processed=total,
                               violations_found=violations_count,
                               completed_at=datetime.now())
        if done_cb:
            done_cb(violations_count, None)

    # ── AUTO-VERIFY (LIVE) ────────────────────────────────────────────────

    def _vkey(self, v):
        """Spatial grid key for a violation."""
        x1,y1,x2,y2 = v.get("bbox",(0,0,100,100))
        return ((x1+x2)//2//self.GRID, (y1+y2)//2//self.GRID, v["type"])

    def _auto_verify(self, frame, v, key, proc_frame, source_type):
        """
        Auto-verification: a violation must be detected VERIFY_HITS times
        within VERIFY_WINDOW processed frames before it's committed to DB.

        This eliminates single-frame false positives automatically.
        """
        # Skip if already cooldown-blocked
        now = time.time()
        if now - self._seen.get(key, 0) < self.COOLDOWN:
            return

        buf = self._verify_buf.get(key)

        if buf is None or proc_frame - buf["first_frame"] > self.VERIFY_WINDOW:
            # Start fresh verification window
            self._verify_buf[key] = {
                "hits":        1,
                "first_frame": proc_frame,
                "committed":   False,
                "last_v":      v,
                "last_frame":  frame.copy(),
            }
            return

        if buf["committed"]:
            return  # already saved for this cooldown window

        buf["hits"]      += 1
        buf["last_v"]     = v
        buf["last_frame"] = frame.copy()

        if buf["hits"] >= self.VERIFY_HITS:
            buf["committed"] = True
            self._seen[key]  = now

            # Plate-level dedup
            plate = v.get("plate","UNKNOWN")
            if plate != "UNKNOWN":
                pk = (plate, v["type"])
                if now - self._seen.get(pk,0) < self.COOLDOWN*2:
                    return
                self._seen[pk] = now

            print(f"[Verify] ✅ Confirmed after {buf['hits']} hits: "
                  f"{v['type']} plate={plate}")
            self._save_violation(buf["last_frame"], v, source_type=source_type)

    # ── SAVE TO DB ────────────────────────────────────────────────────────

    def _save_violation(self, frame, v, source_type="live"):
        """Commit a verified violation — save snapshot + DB record."""
        plate         = v.get("plate","UNKNOWN")
        snap_filename = ""

        if cfg.SAVE_SNAPS:
            os.makedirs(cfg.SNAPSHOT_DIR, exist_ok=True)
            ts    = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            fname = f"{v['type']}_{plate}_{ts}.jpg"
            spath = os.path.join(cfg.SNAPSHOT_DIR, fname)

            x1,y1,x2,y2 = v.get("bbox",(0,0,frame.shape[1],frame.shape[0]))
            m = 60; H,W = frame.shape[:2]
            crop = frame[max(0,y1-m):min(H,y2+m),
                         max(0,x1-m):min(W,x2+m)]
            if crop.size > 0 and cv2.imwrite(spath, crop):
                snap_filename = fname

        if self.db:
            self.db.insert_violation({
                "timestamp":      datetime.now(),
                "violation_type": v["type"],
                "plate_number":   plate,
                "confidence":     v.get("confidence",0),
                "snapshot_path":  snap_filename,
                "location":       cfg.get("camera","location","Camera 1"),
                "source_type":    source_type,
            })

        self.stats["total"] += 1
        if "helmet"   in v["type"]: self.stats["helmet"]   += 1
        if "seatbelt" in v["type"]: self.stats["seatbelt"] += 1
        if self.on_violation:
            self.on_violation(v, snap_filename)

    # ── HUD ───────────────────────────────────────────────────────────────

    def _draw_hud(self, frame):
        h,w = frame.shape[:2]
        ov  = frame.copy()
        cv2.rectangle(ov,(0,0),(w,58),(8,12,18),-1)
        cv2.addWeighted(ov,0.75,frame,0.25,0,frame)
        pending = sum(1 for b in self._verify_buf.values()
                      if not b["committed"])
        cv2.putText(frame,
            f"LIVE  FPS:{self.stats['fps']}  Confirmed:{self.stats['total']}  Verifying:{pending}",
            (10,22),cv2.FONT_HERSHEY_SIMPLEX,0.60,(0,230,120),2)
        cv2.putText(frame,
            f"No Helmet:{self.stats['helmet']}  Auto-verify ON (x{self.VERIFY_HITS} hits)",
            (10,46),cv2.FONT_HERSHEY_SIMPLEX,0.46,(200,180,80),1)
        cv2.circle(frame,(w-22,22),7,(0,0,230),-1)

    def _put_verify_label(self, frame, text, pos):
        x,y = pos; y = max(y-8, 12)
        fs,ft = 0.48,1
        (tw,th),_ = cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,fs,ft)
        cv2.rectangle(frame,(x,y-th-4),(x+tw+6,y+4),(0,160,200),-1)
        cv2.putText(frame,text,(x+3,y),cv2.FONT_HERSHEY_SIMPLEX,fs,(255,255,255),ft)

    def get_frame_b64(self) -> str:
        with self._lock:
            if self._current_frame is None: return ""
            _,buf = cv2.imencode(".jpg",self._current_frame,
                                 [cv2.IMWRITE_JPEG_QUALITY,78])
            return base64.b64encode(buf).decode()