"""
Frame Processor — YOLOv8 Detection Pipeline
Uses custom helmet model (head detection) + COCO model (motorcycle detection).
Only flags RIDER, not passengers.
"""
import cv2
import numpy as np
from typing import List, Tuple, Dict
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FrameProcessor:
    COLORS = {
        "violation": (0, 0, 255),
        "safe":      (0, 220, 80),
        "vehicle":   (255, 140, 0),
        "plate":     (0, 220, 255),
        "passenger": (120, 120, 120),
    }

    HELMET_YES = {
        "with helmet","with-helmet","helmet","helmet on","wearing helmet",
        "head with helmet","head_with_helmet","has helmet","helmet_on","safe",
    }
    HELMET_NO = {
        "without helmet","without-helmet","no helmet","no-helmet",
        "head without helmet","head_without_helmet","no_helmet",
        "helmet off","not wearing helmet","unsafe","nohelmet","helmet_off",
    }

    def __init__(self, confidence=0.40):   # lower threshold = detect more
        self.confidence   = confidence
        self.model        = None
        self.coco_model   = None
        self.plate_model  = None
        self.custom_model = False
        self.class_map    = {}
        self._load_models()

    def _load_models(self):
        try:
            from ultralytics import YOLO
            import config as cfg

            model_path = cfg.HELMET_MODEL or self._find_helmet_model()
            self.model = YOLO(model_path)
            self.custom_model = any(k in str(model_path).lower()
                                    for k in ("helmet","best","trained"))
            if self.custom_model:
                self._build_class_map(self.model.names)
                self.coco_model = YOLO("yolov8n.pt")
                print("[Processor] COCO vehicle detector loaded")

            self.plate_model = YOLO(cfg.PLATE_MODEL or "yolov8n.pt")
            print(f"[Processor] Model: {model_path}  custom={self.custom_model}")

        except ImportError:
            print("[Processor] ultralytics not installed -> demo mode")
        except Exception as e:
            print(f"[Processor] Load error: {e}")

    def _find_helmet_model(self) -> str:
        from pathlib import Path
        import glob
        models_dir = Path(__file__).parent.parent / "models"
        models_dir.mkdir(exist_ok=True)
        for name in ("helmet_yolov8n.pt","helmet_yolov8s.pt","helmet_yolov8m.pt"):
            p = models_dir / name
            if p.exists() and p.stat().st_size > 100_000:
                return str(p)
        base = Path(__file__).parent.parent
        run_pts = glob.glob(str(base/"runs"/"**"/"best.pt"), recursive=True)
        if run_pts:
            latest = max(run_pts, key=lambda p: os.path.getmtime(p))
            return latest
        return "yolov8n.pt"

    def _build_class_map(self, names: dict):
        self.class_map = {}
        for cid, name in names.items():
            n = name.lower().strip()
            if n in self.HELMET_YES:
                self.class_map[cid] = "yes"
            elif n in self.HELMET_NO:
                self.class_map[cid] = "no"
            elif any(k in n for k in ("motorcycle","motorbike","bike","moto")):
                self.class_map[cid] = "moto"
            elif any(k in n for k in ("car","vehicle","truck","suv")):
                self.class_map[cid] = "car"
            else:
                if "helmet" in n and "without" not in n and "no" not in n:
                    self.class_map[cid] = "yes"
                elif any(k in n for k in ("without","no helmet","no_helmet")):
                    self.class_map[cid] = "no"
                else:
                    self.class_map[cid] = "unknown"
        print(f"[Processor] Class map: { {names[k]:v for k,v in self.class_map.items()} }")

    def process(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
        if self.model is None:
            return self._demo_mode(frame), []
        try:
            return self._run_detection(frame)
        except Exception as e:
            print(f"[Processor] Detection error: {e}")
            import traceback; traceback.print_exc()
            return frame.copy(), []

    def _run_detection(self, frame: np.ndarray):
        annotated  = frame.copy()
        violations = []
        H, W       = frame.shape[:2]

        # ── Step 1: Detect heads with helmet model (low threshold) ────────
        results = self.model(frame, conf=0.30, verbose=False)[0]
        persons = []

        for box in results.boxes:
            cls  = int(box.cls[0])
            conf = float(box.conf[0])
            x1,y1,x2,y2 = map(int, box.xyxy[0])
            if self.custom_model:
                role = self.class_map.get(cls, "unknown")
                if role == "yes":
                    persons.append({"bbox":(x1,y1,x2,y2),"conf":conf,"helmet":True})
                elif role == "no":
                    persons.append({"bbox":(x1,y1,x2,y2),"conf":conf,"helmet":False})
            else:
                if cls == 0:
                    persons.append({"bbox":(x1,y1,x2,y2),"conf":conf,"helmet":None})

        # ── Step 2: Detect motorcycles with COCO model ────────────────────
        motorcycles, cars = [], []
        v_src = self.coco_model if self.coco_model else self.model
        v_res = v_src(frame, conf=0.30, verbose=False)[0]

        for box in v_res.boxes:
            cls  = int(box.cls[0])
            conf = float(box.conf[0])
            x1,y1,x2,y2 = map(int, box.xyxy[0])
            if cls == 3:
                motorcycles.append({"bbox":(x1,y1,x2,y2),"conf":conf})
                cv2.rectangle(annotated,(x1,y1),(x2,y2),self.COLORS["vehicle"],2)
            elif cls == 2:
                cars.append({"bbox":(x1,y1,x2,y2),"conf":conf})
                cv2.rectangle(annotated,(x1,y1),(x2,y2),self.COLORS["vehicle"],1)

        # ── Step 3: For each motorcycle find associated heads ──────────────
        flagged = set()

        for moto in motorcycles:
            on_bike = self._heads_on_moto(moto["bbox"], persons, frame_h=H)
            if not on_bike:
                continue

            rider = self._identify_rider(moto["bbox"], on_bike)

            for p in on_bike:
                flagged.add(id(p))
                px1,py1,px2,py2 = p["bbox"]

                if p is rider:
                    has_helmet = p.get("helmet")
                    if has_helmet is None:
                        has_helmet = self._heuristic_helmet(frame, p["bbox"])
                    color = self.COLORS["safe"] if has_helmet else self.COLORS["violation"]
                    label = "HELMET OK" if has_helmet else "NO HELMET"
                    cv2.rectangle(annotated,(px1,py1),(px2,py2),color,3)
                    self._put_label(annotated, label, (px1,py1), color)
                    if not has_helmet:
                        violations.append({
                            "type":"no_helmet","bbox":(px1,py1,px2,py2),
                            "confidence":p["conf"],"plate":"UNKNOWN",
                        })
                else:
                    cv2.rectangle(annotated,(px1,py1),(px2,py2),self.COLORS["passenger"],1)
                    self._put_label(annotated,"PASSENGER",(px1,py1),self.COLORS["passenger"])

        # ── Step 4: Heads not on any motorcycle — label only, no violation ─
        for p in persons:
            if id(p) in flagged:
                continue
            px1,py1,px2,py2 = p["bbox"]
            h = p.get("helmet")
            if h is True:
                cv2.rectangle(annotated,(px1,py1),(px2,py2),self.COLORS["safe"],1)
                self._put_label(annotated,"HELMET OK",(px1,py1),self.COLORS["safe"])
            elif h is False:
                cv2.rectangle(annotated,(px1,py1),(px2,py2),(80,80,80),1)
                self._put_label(annotated,"NO MOTO",(px1,py1),(80,80,80))

        # ── Step 5: Plate reading ──────────────────────────────────────────
        if violations:
            from utils.plate_reader import PlateReader
            pr = PlateReader()
            for v in violations:
                text = pr.read_from_region(frame, v["bbox"], expand=80)
                if text:
                    v["plate"] = text
                    bx1,_,bx2,by2 = v["bbox"]
                    cv2.rectangle(annotated,(bx1,by2),(bx2,by2+26),self.COLORS["plate"],-1)
                    cv2.putText(annotated,text,(bx1+4,by2+20),
                                cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,0,0),2)

        return annotated, violations

    def _heads_on_moto(self, vbbox, persons, frame_h=720):
        """
        Find all heads belonging to this motorcycle.
        
        Key insight: the helmet model detects HEADS (small boxes, ~40-80px).
        The motorcycle box is much larger. The head of a rider sits ABOVE
        or at the TOP of the motorcycle bbox — not inside it like a full body would.
        
        Strategy:
        1. Expand the motorcycle search zone upward (riders sit above the bike)
        2. Use horizontal center proximity (head must be roughly above the bike)
        3. Scale search zone by motorcycle size (far bikes = small boxes)
        """
        mx1,my1,mx2,my2 = vbbox
        mw = mx2-mx1
        mh = my2-my1
        mcx = (mx1+mx2)/2

        # Expand search zone: upward by 1.5x moto height, sideways by 20%
        zone_x1 = mx1 - int(mw*0.20)
        zone_x2 = mx2 + int(mw*0.20)
        zone_y1 = my1 - int(mh*1.5)   # riders' heads are above the bike
        zone_y2 = my2 + int(mh*0.20)  # small overlap below

        result = []
        for p in persons:
            px1,py1,px2,py2 = p["bbox"]
            pcx = (px1+px2)/2
            pcy = (py1+py2)/2

            # Head center must be inside the expanded zone
            in_zone = (zone_x1 <= pcx <= zone_x2 and
                       zone_y1 <= pcy <= zone_y2)
            if in_zone:
                result.append(p)

        return result

    def _identify_rider(self, vbbox, persons):
        """Rider = lowest (highest y) and most centered person on bike."""
        if len(persons) == 1:
            return persons[0]
        mx1,my1,mx2,my2 = vbbox
        mcx = (mx1+mx2)/2
        def score(p):
            px1,py1,px2,py2 = p["bbox"]
            # Rider sits lowest (largest y center) and closest to moto center
            vert  = (py1+py2)/2 / max(my2, 1)
            horiz = 1 - abs((px1+px2)/2 - mcx) / max(mx2-mx1, 1)
            return vert*0.6 + horiz*0.4
        return max(persons, key=score)

    def _heuristic_helmet(self, frame, bbox) -> bool:
        """Fallback heuristic when no custom model. ~60% accuracy."""
        x1,y1,x2,y2 = bbox
        ph=y2-y1; pw=x2-x1
        if ph<30 or pw<15: return False
        mx=int(pw*0.10)
        head=frame[max(0,y1):min(frame.shape[0],y1+int(ph*0.28)),
                   max(0,x1+mx):min(frame.shape[1],x2-mx)]
        if head.size==0 or head.shape[0]<6 or head.shape[1]<6: return False
        hsv  = cv2.cvtColor(head,cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(head,cv2.COLOR_BGR2GRAY)
        skin=(cv2.inRange(hsv,np.array([0,15,50]),  np.array([22,200,255]))|
              cv2.inRange(hsv,np.array([0,20,30]),  np.array([20,220,210]))|
              cv2.inRange(hsv,np.array([168,15,50]),np.array([180,200,255])))
        skin_r=float(np.sum(skin>0))/max(head.shape[0]*head.shape[1],1)
        if skin_r>0.30: return False
        gh,gw=max(head.shape[0]//3,1),max(head.shape[1]//3,1)
        smooth=sum(1 for r in range(3) for c in range(3)
            if gray[r*gh:(r+1)*gh,c*gw:(c+1)*gw].size>0 and
               float(np.std(gray[r*gh:(r+1)*gh,c*gw:(c+1)*gw]))<30)/9
        h_ch=hsv[:,:,0].flatten().astype(int)
        dom=float(np.max(np.bincount(h_ch,minlength=180)))/max(len(h_ch),1)
        return smooth*0.45+dom*0.35+(1-skin_r)*0.20>0.58

    def _demo_mode(self, frame):
        out=frame.copy(); h,w=frame.shape[:2]
        cv2.rectangle(out,(0,0),(w,55),(15,15,15),-1)
        cv2.putText(out,"DEMO — pip install ultralytics",
                    (10,22),cv2.FONT_HERSHEY_SIMPLEX,0.65,(0,220,220),2)
        return out

    def _put_label(self, frame, text, pos, color):
        x,y=pos; fs,ft=0.52,2
        (tw,th),_=cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,fs,ft)
        y=max(y,th+6)
        cv2.rectangle(frame,(x,y-th-5),(x+tw+6,y+4),color,-1)
        cv2.putText(frame,text,(x+3,y),cv2.FONT_HERSHEY_SIMPLEX,fs,(255,255,255),ft)