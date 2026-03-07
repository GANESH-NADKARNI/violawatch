"""
ViolaWatch — Desktop GUI Application
Built with Tkinter + CustomTkinter for a modern dark-theme interface
"""
import sys, os, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    print("[GUI] customtkinter not found, using standard tkinter")

from core.detector import ViolationDetector
from database.db_manager import DatabaseManager
import config as cfg

# ── Color palette ──────────────────────────────────────────────────────────
DARK    = "#0a0e1a"
DARKER  = "#060910"
PANEL   = "#0d1424"
BORDER  = "#1a2840"
ACCENT  = "#00b4d8"
RED     = "#e63946"
AMBER   = "#f4a261"
GREEN   = "#2ec4b6"
TEXT    = "#c8d8e8"
TEXT2   = "#6a8ba5"
WHITE   = "#e8f4f8"
FONT_MONO = ("Consolas", 10)
FONT_HEAD = ("Segoe UI", 11, "bold")
FONT_BIG  = ("Segoe UI", 22, "bold")


class ViolaWatchApp:
    def __init__(self):
        self.db = DatabaseManager()
        self.detector = ViolationDetector(
            db=self.db,
            on_violation=self._on_violation_callback
        )
        self.root = tk.Tk()
        self._build_window()
        self._build_layout()
        self._load_stats()
        self._load_violations()

        # Auto-refresh every 4s
        self._refresh_loop()

    def _build_window(self):
        self.root.title("ViolaWatch — Traffic Violation Detection")
        self.root.geometry("1400x860")
        self.root.minsize(1100, 700)
        self.root.configure(bg=DARKER)
        try:
            self.root.iconbitmap("")
        except Exception:
            pass

    # ── LAYOUT ────────────────────────────────────────────────────────────

    def _build_layout(self):
        # ── Top bar ──
        topbar = tk.Frame(self.root, bg=DARK, height=52)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)
        tk.Label(topbar, text="🎯 ViolaWatch", bg=DARK, fg=WHITE,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=20, pady=14)
        tk.Label(topbar, text="Real-Time Traffic Violation Detection System",
                 bg=DARK, fg=TEXT2, font=("Segoe UI",10)).pack(side="left")

        self.live_badge = tk.Label(topbar, text="● STANDBY", bg=DARK,
                                    fg=TEXT2, font=FONT_MONO)
        self.live_badge.pack(side="right", padx=20)

        # ── Main 3-column layout ──
        body = tk.Frame(self.root, bg=DARKER)
        body.pack(fill="both", expand=True)

        # Left sidebar
        self.sidebar = tk.Frame(body, bg=DARK, width=230)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Center content
        center = tk.Frame(body, bg=DARKER)
        center.pack(side="left", fill="both", expand=True)

        # Right detail panel
        self.detail_frame = tk.Frame(body, bg=DARK, width=300)
        self.detail_frame.pack(side="right", fill="y")
        self.detail_frame.pack_propagate(False)

        self._build_sidebar()
        self._build_center(center)
        self._build_detail_panel()

    def _build_sidebar(self):
        s = self.sidebar
        pad = {"padx": 12, "pady": 4}

        tk.Label(s, text="STATISTICS", bg=DARK, fg=TEXT2,
                 font=("Consolas",9)).pack(anchor="w", padx=12, pady=(14,4))

        self.stat_total_var  = tk.StringVar(value="—")
        self.stat_today_var  = tk.StringVar(value="—")
        self.stat_helmet_var = tk.StringVar(value="—")
        self.stat_belt_var   = tk.StringVar(value="—")

        for label, var, color in [
            ("Total Violations", self.stat_total_var,  ACCENT),
            ("Today",            self.stat_today_var,  RED),
            ("No Helmet",        self.stat_helmet_var, RED),
            ("No Seatbelt",      self.stat_belt_var,   AMBER),
        ]:
            card = tk.Frame(s, bg=PANEL, highlightbackground=BORDER,
                            highlightthickness=1)
            card.pack(fill="x", **pad)
            tk.Label(card, text=label, bg=PANEL, fg=TEXT2,
                     font=("Segoe UI",9)).pack(anchor="w", padx=8, pady=(6,0))
            tk.Label(card, textvariable=var, bg=PANEL, fg=color,
                     font=("Segoe UI",24,"bold")).pack(anchor="w", padx=8, pady=(0,6))

        # Separator
        tk.Frame(s, bg=BORDER, height=1).pack(fill="x", padx=12, pady=8)

        # ── Camera Control ──
        tk.Label(s, text="CAMERA", bg=DARK, fg=TEXT2,
                 font=("Consolas",9)).pack(anchor="w", padx=12, pady=(0,4))

        src_frame = tk.Frame(s, bg=DARK)
        src_frame.pack(fill="x", padx=12, pady=(0,6))
        tk.Label(src_frame, text="Source:", bg=DARK, fg=TEXT2,
                 font=("Segoe UI",9)).pack(anchor="w")
        self.cam_source_var = tk.StringVar(value="0")
        src_entry = tk.Entry(src_frame, textvariable=self.cam_source_var,
                              bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              relief="flat", font=FONT_MONO,
                              highlightbackground=BORDER, highlightthickness=1)
        src_entry.pack(fill="x", ipady=5)

        self.btn_start = tk.Button(s, text="▶  START DETECTION",
                                    bg="#0d3d1a", fg=GREEN, activebackground="#0a2e14",
                                    font=("Segoe UI",10,"bold"), relief="flat",
                                    cursor="hand2", command=self._start_camera)
        self.btn_start.pack(fill="x", padx=12, pady=2, ipady=7)

        self.btn_stop = tk.Button(s, text="■  STOP",
                                   bg="#3d0d0d", fg=RED, activebackground="#2e0a0a",
                                   font=("Segoe UI",10,"bold"), relief="flat",
                                   cursor="hand2", command=self._stop_camera,
                                   state="disabled")
        self.btn_stop.pack(fill="x", padx=12, pady=2, ipady=7)

        # Separator
        tk.Frame(s, bg=BORDER, height=1).pack(fill="x", padx=12, pady=8)

        # ── Video Upload ──
        tk.Label(s, text="VIDEO UPLOAD (TEST)", bg=DARK, fg=TEXT2,
                 font=("Consolas",9)).pack(anchor="w", padx=12, pady=(0,4))

        tk.Button(s, text="📂  Upload Video File",
                  bg="#1a1a3d", fg=ACCENT, activebackground="#14142e",
                  font=("Segoe UI",10), relief="flat", cursor="hand2",
                  command=self._upload_video).pack(fill="x", padx=12, pady=2, ipady=7)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label = tk.Label(s, text="", bg=DARK, fg=TEXT2,
                                        font=("Consolas",9))
        self.progress_label.pack(anchor="w", padx=12)

        self.progress_bar = ttk.Progressbar(s, variable=self.progress_var,
                                             maximum=100, mode="determinate",
                                             length=200)
        self.progress_bar.pack(fill="x", padx=12, pady=(2,8))

        # Separator
        tk.Frame(s, bg=BORDER, height=1).pack(fill="x", padx=12, pady=4)

        # ── Filters ──
        tk.Label(s, text="FILTERS", bg=DARK, fg=TEXT2,
                 font=("Consolas",9)).pack(anchor="w", padx=12, pady=(4,4))

        self.filter_type_var = tk.StringVar(value="All")
        tk.Label(s, text="Type:", bg=DARK, fg=TEXT2,
                 font=("Segoe UI",9)).pack(anchor="w", padx=12)
        self.type_combo = ttk.Combobox(s, textvariable=self.filter_type_var,
                                        values=["All","No Helmet","No Seatbelt"],
                                        state="readonly", font=("Segoe UI",9))
        self.type_combo.pack(fill="x", padx=12, pady=(0,6))
        self.type_combo.bind("<<ComboboxSelected>>", lambda _: self._load_violations())

        self.filter_plate_var = tk.StringVar()
        tk.Label(s, text="Plate:", bg=DARK, fg=TEXT2,
                 font=("Segoe UI",9)).pack(anchor="w", padx=12)
        plate_entry = tk.Entry(s, textvariable=self.filter_plate_var,
                                bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                relief="flat", font=FONT_MONO,
                                highlightbackground=BORDER, highlightthickness=1)
        plate_entry.pack(fill="x", padx=12, ipady=5)
        plate_entry.bind("<Return>", lambda _: self._load_violations())

        tk.Button(s, text="Apply Filters", bg=PANEL, fg=TEXT,
                  relief="flat", cursor="hand2",
                  command=self._load_violations).pack(fill="x", padx=12, pady=(6,2), ipady=5)
        tk.Button(s, text="Clear", bg=DARKER, fg=TEXT2,
                  relief="flat", cursor="hand2",
                  command=self._clear_filters).pack(fill="x", padx=12, pady=2, ipady=4)

        # Demo seed button
        tk.Frame(s, bg=BORDER, height=1).pack(fill="x", padx=12, pady=8)
        tk.Button(s, text="🎲 Load Demo Data", bg=DARKER, fg=TEXT2,
                  relief="flat", cursor="hand2",
                  command=self._seed_demo).pack(fill="x", padx=12, ipady=4)

    def _build_center(self, parent):
        # ── Camera feed (top) ──
        feed_frame = tk.Frame(parent, bg=DARKER)
        feed_frame.pack(fill="x", padx=8, pady=(8,4))

        cam_border = tk.Frame(feed_frame, bg=BORDER)
        cam_border.pack(fill="x")

        self.cam_label = tk.Label(cam_border, bg="#060a10",
                                   text="📷  NO FEED — Click START DETECTION or Upload a video",
                                   fg=TEXT2, font=("Segoe UI",11), height=14)
        self.cam_label.pack(fill="x")

        # ── Violations table (bottom) ──
        table_frame = tk.Frame(parent, bg=DARKER)
        table_frame.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # Header
        hdr = tk.Frame(table_frame, bg=PANEL)
        hdr.pack(fill="x")
        tk.Label(hdr, text="VIOLATIONS LOG", bg=PANEL, fg=TEXT,
                 font=("Segoe UI",11,"bold")).pack(side="left", padx=12, pady=8)
        self.count_label = tk.Label(hdr, text="0 records", bg=PANEL, fg=ACCENT,
                                     font=FONT_MONO)
        self.count_label.pack(side="left", padx=4)
        tk.Button(hdr, text="↻ Refresh", bg=PANEL, fg=ACCENT, relief="flat",
                  cursor="hand2", command=self._load_violations).pack(side="right", padx=12)

        # Style table
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("VW.Treeview",
                         background=PANEL, foreground=TEXT,
                         fieldbackground=PANEL, rowheight=28,
                         font=("Segoe UI",9),
                         borderwidth=0)
        style.configure("VW.Treeview.Heading",
                         background=DARKER, foreground=TEXT2,
                         font=("Consolas",9,"bold"), borderwidth=0,
                         relief="flat")
        style.map("VW.Treeview",
                  background=[("selected","#1a2840")],
                  foreground=[("selected",ACCENT)])

        cols = ("id","type","plate","location","time","conf","status")
        self.tree = ttk.Treeview(table_frame, columns=cols,
                                  show="headings", style="VW.Treeview",
                                  selectmode="browse")

        widths = {"id":50,"type":140,"plate":130,"location":160,
                  "time":145,"conf":70,"status":90}
        for c in cols:
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=widths[c], minwidth=40, anchor="w")

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                             command=self.tree.yview)
        self.tree.configure(yscroll=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("helmet",   foreground="#ff6b6b")
        self.tree.tag_configure("seatbelt", foreground="#ffa94d")
        self.tree.tag_configure("reviewed", foreground=TEXT2)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Pagination
        pg_frame = tk.Frame(parent, bg=PANEL)
        pg_frame.pack(fill="x", padx=8, pady=(0,4))
        self.prev_btn = tk.Button(pg_frame, text="← Prev", bg=PANEL, fg=TEXT,
                                   relief="flat", cursor="hand2",
                                   command=self._prev_page, state="disabled")
        self.prev_btn.pack(side="left", padx=8, pady=4)
        self.page_label = tk.Label(pg_frame, text="Page 1 / 1", bg=PANEL,
                                    fg=TEXT2, font=FONT_MONO)
        self.page_label.pack(side="left")
        self.next_btn = tk.Button(pg_frame, text="Next →", bg=PANEL, fg=TEXT,
                                   relief="flat", cursor="hand2",
                                   command=self._next_page, state="disabled")
        self.next_btn.pack(side="left", padx=8)

    def _build_detail_panel(self):
        d = self.detail_frame
        tk.Label(d, text="VIOLATION DETAIL", bg=DARK, fg=TEXT2,
                 font=("Consolas",9)).pack(anchor="w", padx=12, pady=(14,6))
        tk.Frame(d, bg=BORDER, height=1).pack(fill="x", padx=12, pady=(0,8))

        # Snapshot
        self.snap_label = tk.Label(d, bg="#060a10", text="No snapshot",
                                    fg=TEXT2, font=("Segoe UI",10), height=9)
        self.snap_label.pack(fill="x", padx=12)

        self.snap_img_ref = None

        # Detail fields
        self.detail_vars = {}
        fields = [
            ("ID",           "id"),
            ("Violation",    "violation_type"),
            ("Plate",        "plate_number"),
            ("Confidence",   "confidence"),
            ("Timestamp",    "timestamp"),
            ("Location",     "location"),
            ("Source",       "source_type"),
        ]

        for label, key in fields:
            row = tk.Frame(d, bg=DARK)
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=label+":", bg=DARK, fg=TEXT2,
                     font=("Segoe UI",9), width=10, anchor="w").pack(side="left")
            var = tk.StringVar(value="—")
            self.detail_vars[key] = var
            tk.Label(row, textvariable=var, bg=DARK, fg=TEXT,
                     font=("Segoe UI",9,"bold"), anchor="w",
                     wraplength=170).pack(side="left", fill="x")

        tk.Frame(d, bg=BORDER, height=1).pack(fill="x", padx=12, pady=10)

        # Status change
        tk.Label(d, text="STATUS", bg=DARK, fg=TEXT2,
                 font=("Consolas",9)).pack(anchor="w", padx=12, pady=(0,4))
        self.status_var = tk.StringVar(value="pending")
        for s,lbl in [("pending","⏳ Pending"),("reviewed","✅ Reviewed"),("dismissed","❌ Dismissed")]:
            tk.Radiobutton(d, text=lbl, variable=self.status_var, value=s,
                           bg=DARK, fg=TEXT, selectcolor=PANEL,
                           activebackground=DARK, font=("Segoe UI",9)).pack(anchor="w", padx=16)

        tk.Button(d, text="💾 Save Status", bg="#0d2f3d", fg=ACCENT,
                  relief="flat", cursor="hand2",
                  command=self._save_status).pack(fill="x", padx=12, pady=(8,4), ipady=6)

        tk.Button(d, text="🗑 Delete Record", bg="#3d0d0d", fg=RED,
                  relief="flat", cursor="hand2",
                  command=self._delete_violation).pack(fill="x", padx=12, pady=2, ipady=6)

        tk.Button(d, text="📤 Export CSV", bg=DARKER, fg=TEXT2,
                  relief="flat", cursor="hand2",
                  command=self._export_csv).pack(fill="x", padx=12, pady=2, ipady=5)

        self._selected_id = None

    # ── CAMERA ────────────────────────────────────────────────────────────

    def _start_camera(self):
        src = self.cam_source_var.get().strip()
        source = int(src) if src.isdigit() else src
        try:
            self.detector.start_live(source)
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
            self.live_badge.config(text="● LIVE", fg=GREEN)
            self._start_frame_update()
        except Exception as e:
            messagebox.showerror("Camera Error", str(e))

    def _stop_camera(self):
        self.detector.stop()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.live_badge.config(text="● STANDBY", fg=TEXT2)
        self.cam_label.config(image="", text="📷  Feed stopped")

    def _start_frame_update(self):
        def _update():
            if not self.detector.is_running:
                return
            b64 = self.detector.get_frame_b64()
            if b64:
                import base64
                from io import BytesIO
                data = base64.b64decode(b64)
                img = Image.open(BytesIO(data))
                # Fit to label width
                lw = max(self.cam_label.winfo_width(), 640)
                ratio = lw / img.width
                nh = int(img.height * ratio)
                img = img.resize((lw, nh), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.cam_label.config(image=photo, text="")
                self.cam_label._img = photo
                fps = self.detector.stats["fps"]
                self.live_badge.config(
                    text=f"● LIVE  {fps} FPS  Violations: {self.detector.stats['total']}")
            self.root.after(120, _update)
        self.root.after(120, _update)

    # ── VIDEO UPLOAD ──────────────────────────────────────────────────────

    def _upload_video(self):
        path = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[("Video files","*.mp4 *.avi *.mov *.mkv *.wmv"),
                       ("All files","*.*")]
        )
        if not path: return

        job_id = self.db.create_job(os.path.basename(path))
        self.progress_var.set(0)
        self.progress_label.config(text=f"Processing: {os.path.basename(path)}")

        def on_progress(pct, frames, viols):
            self.progress_var.set(pct)
            self.progress_label.config(
                text=f"{pct}% — {frames} frames — {viols} violations")

        def on_done(viols, err):
            if err:
                self.progress_label.config(text=f"Error: {err}")
            else:
                self.progress_var.set(100)
                self.progress_label.config(text=f"Done! Found {viols} violations")
                self.root.after(500, self._load_violations)
                self.root.after(500, self._load_stats)
                messagebox.showinfo("Processing Complete",
                    f"Video analysis complete.\nFound {viols} violations.")

        self.detector.process_video_file(path, job_id,
                                          progress_cb=on_progress,
                                          done_cb=on_done)

        # Start showing frames during processing
        self._start_frame_update_once()

    def _start_frame_update_once(self):
        def _update():
            b64 = self.detector.get_frame_b64()
            if b64:
                import base64
                from io import BytesIO
                data = base64.b64decode(b64)
                img = Image.open(BytesIO(data))
                lw = max(self.cam_label.winfo_width(), 640)
                ratio = lw / img.width
                nh = int(img.height * ratio)
                img = img.resize((lw, nh), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.cam_label.config(image=photo, text="")
                self.cam_label._img = photo
            # Keep going as long as there's a frame
            if b64:
                self.root.after(200, _update)
        self.root.after(200, _update)

    # ── VIOLATIONS TABLE ──────────────────────────────────────────────────

    def _load_violations(self):
        vtype = self.filter_type_var.get()
        plate = self.filter_plate_var.get().strip()
        type_map = {"No Helmet":"no_helmet","No Seatbelt":"no_seatbelt","All":None}
        vtype_key = type_map.get(vtype)

        limit = 50
        offset = (getattr(self,"_page",1)-1) * limit
        records = self.db.get_violations(limit=limit, offset=offset,
                                          violation_type=vtype_key,
                                          plate=plate or None)
        total = self.db.count_violations(violation_type=vtype_key,
                                          plate=plate or None)
        pages = max(1,(total+limit-1)//limit)
        page  = getattr(self,"_page",1)

        self.page_label.config(text=f"Page {page} / {pages}")
        self.prev_btn.config(state="normal" if page>1 else "disabled")
        self.next_btn.config(state="normal" if page<pages else "disabled")
        self._total_pages = pages
        self.count_label.config(text=f"{total} records")

        self.tree.delete(*self.tree.get_children())
        for r in records:
            ts = str(r.get("timestamp",""))[:19]
            conf = f"{int(float(r.get('confidence',0))*100)}%"
            tag = "helmet" if "helmet" in r.get("violation_type","") else "seatbelt"
            if r.get("status") == "reviewed": tag = "reviewed"
            vtype_disp = "🪖 No Helmet" if "helmet" in r["violation_type"] else "🚗 No Seatbelt"
            self.tree.insert("","end",
                iid=str(r["id"]),
                values=(r["id"], vtype_disp, r.get("plate_number","?"),
                        r.get("location",""), ts, conf, r.get("status","pending")),
                tags=(tag,)
            )

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel: return
        vid = int(sel[0])
        self._selected_id = vid
        r = self.db.get_violation_by_id(vid)
        if not r: return
        mapping = {
            "id": str(r.get("id","")),
            "violation_type": "🪖 No Helmet" if "helmet" in r.get("violation_type","") else "🚗 No Seatbelt",
            "plate_number": r.get("plate_number","UNKNOWN"),
            "confidence": f"{int(float(r.get('confidence',0))*100)}%",
            "timestamp": str(r.get("timestamp",""))[:19],
            "location": r.get("location",""),
            "source_type": r.get("source_type","live"),
        }
        for k,v in mapping.items():
            self.detail_vars[k].set(v)
        self.status_var.set(r.get("status","pending"))

        # Load snapshot
        snap = r.get("snapshot_path","")
        if snap and os.path.exists(snap):
            try:
                img = Image.open(snap)
                img.thumbnail((276, 155), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.snap_label.config(image=photo, text="")
                self.snap_img_ref = photo
            except Exception:
                self.snap_label.config(image="", text="Snapshot unavailable")
        else:
            self.snap_label.config(image="", text="No snapshot")

    def _prev_page(self):
        self._page = max(1, getattr(self,"_page",1)-1)
        self._load_violations()

    def _next_page(self):
        tp = getattr(self,"_total_pages",1)
        self._page = min(tp, getattr(self,"_page",1)+1)
        self._load_violations()

    # ── STATS ──────────────────────────────────────────────────────────────

    def _load_stats(self):
        s = self.db.get_stats()
        self.stat_total_var.set(str(s.get("total",0)))
        self.stat_today_var.set(str(s.get("today",0)))
        bt = s.get("by_type",{})
        self.stat_helmet_var.set(str(bt.get("no_helmet",0)))
        self.stat_belt_var.set(str(bt.get("no_seatbelt",0)))

    # ── ACTIONS ──────────────────────────────────────────────────────────

    def _save_status(self):
        if self._selected_id is None:
            messagebox.showwarning("No selection","Select a violation first")
            return
        self.db.update_violation(self._selected_id, self.status_var.get())
        self._load_violations()

    def _delete_violation(self):
        if self._selected_id is None: return
        if messagebox.askyesno("Confirm","Delete this violation record?"):
            self.db.delete_violation(self._selected_id)
            self._selected_id = None
            for k in self.detail_vars:
                self.detail_vars[k].set("—")
            self._load_violations()
            self._load_stats()

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV","*.csv")],
            title="Export violations"
        )
        if not path: return
        import csv
        records = self.db.get_violations(limit=10000)
        with open(path,"w",newline="",encoding="utf-8") as f:
            if records:
                w = csv.DictWriter(f, fieldnames=records[0].keys())
                w.writeheader()
                w.writerows(records)
        messagebox.showinfo("Exported", f"Saved {len(records)} records to {path}")

    def _clear_filters(self):
        self.filter_type_var.set("All")
        self.filter_plate_var.set("")
        self._page = 1
        self._load_violations()

    def _seed_demo(self):
        self.db.seed_demo()
        self._load_stats()
        self._load_violations()

    def _on_violation_callback(self, v, snap_path):
        """Called from detector thread when new violation found."""
        self.root.after(0, self._load_violations)
        self.root.after(0, self._load_stats)

    def _refresh_loop(self):
        self._load_stats()
        self.root.after(5000, self._refresh_loop)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ViolaWatchApp()
    app.run()
