# """
# MySQL Database Manager for ViolaWatch
# Handles all DB operations with connection pooling
# """
# import sys, os
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import mysql.connector
# from mysql.connector import pooling
# from datetime import datetime, timedelta
# from typing import List, Dict, Optional
# import config as cfg


# class DatabaseManager:
#     _pool = None

#     def __init__(self):
#         self._ensure_pool()

#     def _ensure_pool(self):
#         if DatabaseManager._pool is None:
#             try:
#                 DatabaseManager._pool = pooling.MySQLConnectionPool(
#                     pool_name="violawatch_pool",
#                     pool_size=5,
#                     pool_reset_session=True,
#                     host=cfg.DB_HOST,
#                     port=cfg.DB_PORT,
#                     user=cfg.DB_USER,
#                     password=cfg.DB_PASSWORD,
#                     database=cfg.DB_NAME,
#                     autocommit=True,
#                     charset="utf8mb4",
#                 )
#                 print(f"[DB] MySQL pool connected → {cfg.DB_HOST}:{cfg.DB_PORT}/{cfg.DB_NAME}")
#             except Exception as e:
#                 print(f"[DB] MySQL connection failed: {e}")
#                 print("[DB] Falling back to SQLite...")
#                 DatabaseManager._pool = None
#                 self._init_sqlite()
#                 return
#         self._init_schema()

#     def _init_sqlite(self):
#         """SQLite fallback if MySQL unavailable."""
#         import sqlite3
#         from pathlib import Path
#         self.sqlite_path = str(Path(__file__).parent.parent / "violawatch_fallback.db")
#         self._use_sqlite = True
#         conn = sqlite3.connect(self.sqlite_path)
#         self._sqlite_create_tables(conn)
#         conn.close()
#         print(f"[DB] SQLite fallback active: {self.sqlite_path}")

#     def _get_conn(self):
#         if getattr(self, '_use_sqlite', False):
#             import sqlite3
#             conn = sqlite3.connect(self.sqlite_path)
#             conn.row_factory = sqlite3.Row
#             return conn, True
#         return DatabaseManager._pool.get_connection(), False

#     def _init_schema(self):
#         try:
#             conn, _ = self._get_conn()
#             c = conn.cursor()
#             c.execute(f"CREATE DATABASE IF NOT EXISTS `{cfg.DB_NAME}` CHARACTER SET utf8mb4")
#             c.execute(f"USE `{cfg.DB_NAME}`")
#             self._create_tables_mysql(c)
#             conn.commit()
#             conn.close()
#         except Exception as e:
#             print(f"[DB] Schema init error: {e}")

#     def _create_tables_mysql(self, cursor):
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS violations (
#                 id            INT AUTO_INCREMENT PRIMARY KEY,
#                 timestamp     DATETIME NOT NULL,
#                 violation_type VARCHAR(50) NOT NULL,
#                 plate_number  VARCHAR(20) DEFAULT 'UNKNOWN',
#                 confidence    FLOAT DEFAULT 0.0,
#                 snapshot_path TEXT,
#                 location      VARCHAR(100) DEFAULT 'Camera 1',
#                 source_type   VARCHAR(20) DEFAULT 'live',
#                 status        VARCHAR(20) DEFAULT 'pending',
#                 notes         TEXT,
#                 created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
#                 INDEX idx_ts (timestamp),
#                 INDEX idx_plate (plate_number),
#                 INDEX idx_type (violation_type),
#                 INDEX idx_status (status)
#             ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
#         """)
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS video_jobs (
#                 id          INT AUTO_INCREMENT PRIMARY KEY,
#                 filename    VARCHAR(255) NOT NULL,
#                 status      VARCHAR(20) DEFAULT 'queued',
#                 total_frames INT DEFAULT 0,
#                 processed   INT DEFAULT 0,
#                 violations_found INT DEFAULT 0,
#                 created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
#                 completed_at DATETIME,
#                 error_msg   TEXT
#             ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
#         """)

#     def _sqlite_create_tables(self, conn):
#         conn.executescript("""
#             CREATE TABLE IF NOT EXISTS violations (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 timestamp TEXT NOT NULL,
#                 violation_type TEXT NOT NULL,
#                 plate_number TEXT DEFAULT 'UNKNOWN',
#                 confidence REAL DEFAULT 0.0,
#                 snapshot_path TEXT,
#                 location TEXT DEFAULT 'Camera 1',
#                 source_type TEXT DEFAULT 'live',
#                 status TEXT DEFAULT 'pending',
#                 notes TEXT,
#                 created_at TEXT DEFAULT CURRENT_TIMESTAMP
#             );
#             CREATE TABLE IF NOT EXISTS video_jobs (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 filename TEXT NOT NULL,
#                 status TEXT DEFAULT 'queued',
#                 total_frames INTEGER DEFAULT 0,
#                 processed INTEGER DEFAULT 0,
#                 violations_found INTEGER DEFAULT 0,
#                 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
#                 completed_at TEXT,
#                 error_msg TEXT
#             );
#             CREATE INDEX IF NOT EXISTS idx_ts ON violations(timestamp);
#             CREATE INDEX IF NOT EXISTS idx_plate ON violations(plate_number);
#         """)
#         conn.commit()

#     # ── VIOLATIONS CRUD ──────────────────────────────────────────────────

#     def insert_violation(self, data: dict) -> int:
#         conn, is_sqlite = self._get_conn()
#         try:
#             c = conn.cursor()
#             if is_sqlite:
#                 c.execute("""
#                     INSERT INTO violations (timestamp,violation_type,plate_number,confidence,snapshot_path,location,source_type)
#                     VALUES (?,?,?,?,?,?,?)
#                 """, (
#                     data.get("timestamp", datetime.now().isoformat()),
#                     data["violation_type"], data.get("plate_number","UNKNOWN"),
#                     data.get("confidence",0.0), data.get("snapshot_path",""),
#                     data.get("location","Camera 1"), data.get("source_type","live"),
#                 ))
#                 conn.commit()
#                 return c.lastrowid
#             else:
#                 c.execute("""
#                     INSERT INTO violations (timestamp,violation_type,plate_number,confidence,snapshot_path,location,source_type)
#                     VALUES (%s,%s,%s,%s,%s,%s,%s)
#                 """, (
#                     data.get("timestamp", datetime.now()),
#                     data["violation_type"], data.get("plate_number","UNKNOWN"),
#                     data.get("confidence",0.0), data.get("snapshot_path",""),
#                     data.get("location","Camera 1"), data.get("source_type","live"),
#                 ))
#                 conn.commit()
#                 return c.lastrowid
#         finally:
#             conn.close()

#     def get_violations(self, limit=25, offset=0, violation_type=None,
#                        plate=None, date_from=None, date_to=None, source_type=None) -> List[Dict]:
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             q = "SELECT * FROM violations WHERE 1=1"
#             params = []
#             if violation_type:
#                 q += f" AND violation_type={ph}"; params.append(violation_type)
#             if plate:
#                 q += f" AND plate_number LIKE {ph}"; params.append(f"%{plate}%")
#             if date_from:
#                 q += f" AND timestamp>={ph}"; params.append(date_from)
#             if date_to:
#                 q += f" AND timestamp<={ph}"; params.append(date_to)
#             if source_type:
#                 q += f" AND source_type={ph}"; params.append(source_type)
#             q += f" ORDER BY timestamp DESC LIMIT {ph} OFFSET {ph}"
#             params += [limit, offset]
#             c.execute(q, params)
#             cols = [d[0] for d in c.description]
#             return [dict(zip(cols, row)) for row in c.fetchall()]
#         finally:
#             conn.close()

#     def get_violation_by_id(self, vid: int) -> Optional[Dict]:
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             c.execute(f"SELECT * FROM violations WHERE id={ph}", (vid,))
#             cols = [d[0] for d in c.description]
#             row = c.fetchone()
#             return dict(zip(cols, row)) if row else None
#         finally:
#             conn.close()

#     def count_violations(self, violation_type=None, plate=None) -> int:
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             q = "SELECT COUNT(*) FROM violations WHERE 1=1"
#             params = []
#             if violation_type:
#                 q += f" AND violation_type={ph}"; params.append(violation_type)
#             if plate:
#                 q += f" AND plate_number LIKE {ph}"; params.append(f"%{plate}%")
#             c.execute(q, params)
#             return c.fetchone()[0]
#         finally:
#             conn.close()

#     def update_violation(self, vid: int, status: str, notes: str = None):
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             c.execute(f"UPDATE violations SET status={ph}, notes={ph} WHERE id={ph}",
#                       (status, notes, vid))
#             conn.commit()
#         finally:
#             conn.close()

#     def delete_violation(self, vid: int):
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             c.execute(f"DELETE FROM violations WHERE id={ph}", (vid,))
#             conn.commit()
#         finally:
#             conn.close()

#     def delete_all_violations(self):
#         conn, is_sqlite = self._get_conn()
#         try:
#             c = conn.cursor()
#             c.execute("DELETE FROM violations")
#             conn.commit()
#         finally:
#             conn.close()

#     def delete_job(self, job_id: int):
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             c.execute(f"DELETE FROM video_jobs WHERE id={ph}", (job_id,))
#             conn.commit()
#         finally:
#             conn.close()

#     def get_stats(self) -> Dict:
#         conn, is_sqlite = self._get_conn()
#         try:
#             c = conn.cursor()
#             c.execute("SELECT COUNT(*) FROM violations")
#             total = c.fetchone()[0]

#             if is_sqlite:
#                 c.execute("SELECT COUNT(*) FROM violations WHERE date(timestamp)=date('now')")
#             else:
#                 c.execute("SELECT COUNT(*) FROM violations WHERE DATE(timestamp)=CURDATE()")
#             today = c.fetchone()[0]

#             c.execute("SELECT violation_type, COUNT(*) FROM violations GROUP BY violation_type")
#             by_type = dict(c.fetchall())

#             if is_sqlite:
#                 c.execute("""
#                     SELECT date(timestamp) as day, COUNT(*) as cnt FROM violations
#                     WHERE timestamp >= date('now','-6 days') GROUP BY day ORDER BY day
#                 """)
#             else:
#                 c.execute("""
#                     SELECT DATE(timestamp) as day, COUNT(*) as cnt FROM violations
#                     WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 6 DAY)
#                     GROUP BY day ORDER BY day
#                 """)
#             trend = [{"day": str(r[0]), "count": r[1]} for r in c.fetchall()]

#             c.execute("SELECT * FROM violations ORDER BY timestamp DESC LIMIT 5")
#             cols = [d[0] for d in c.description]
#             recent = [dict(zip(cols, r)) for r in c.fetchall()]

#             return {"total": total, "today": today, "by_type": by_type,
#                     "trend": trend, "recent": recent}
#         finally:
#             conn.close()

#     # ── VIDEO JOBS ───────────────────────────────────────────────────────

#     def create_job(self, filename: str) -> int:
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             c.execute(f"INSERT INTO video_jobs (filename) VALUES ({ph})", (filename,))
#             conn.commit()
#             return c.lastrowid
#         finally:
#             conn.close()

#     def update_job(self, job_id: int, **kwargs):
#         if not kwargs: return
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             sets = ", ".join(f"{k}={ph}" for k in kwargs)
#             vals = list(kwargs.values()) + [job_id]
#             c.execute(f"UPDATE video_jobs SET {sets} WHERE id={ph}", vals)
#             conn.commit()
#         finally:
#             conn.close()

#     def get_job(self, job_id: int) -> Optional[Dict]:
#         conn, is_sqlite = self._get_conn()
#         ph = "?" if is_sqlite else "%s"
#         try:
#             c = conn.cursor()
#             c.execute(f"SELECT * FROM video_jobs WHERE id={ph}", (job_id,))
#             cols = [d[0] for d in c.description]
#             row = c.fetchone()
#             return dict(zip(cols, row)) if row else None
#         finally:
#             conn.close()

#     def get_all_jobs(self) -> List[Dict]:
#         conn, is_sqlite = self._get_conn()
#         try:
#             c = conn.cursor()
#             c.execute("SELECT * FROM video_jobs ORDER BY created_at DESC LIMIT 20")
#             cols = [d[0] for d in c.description]
#             return [dict(zip(cols, r)) for r in c.fetchall()]
#         finally:
#             conn.close()

#     def seed_demo(self):
#         import random
#         plates = ["MH12AB1234","KA05MJ5678","DL3CAF4449","TN09AZ1122","UP32GH9900","UNKNOWN"]
#         types  = ["no_helmet","no_seatbelt","no_helmet"]
#         locs   = ["Junction A - Cam1","Highway Exit - Cam3","School Zone - Cam2"]
#         for i in range(60):
#             dt = datetime.now() - timedelta(days=random.randint(0,6),
#                  hours=random.randint(0,23), minutes=random.randint(0,59))
#             self.insert_violation({
#                 "timestamp": dt, "violation_type": random.choice(types),
#                 "plate_number": random.choice(plates),
#                 "confidence": round(random.uniform(0.6, 0.97), 2),
#                 "location": random.choice(locs), "source_type": "demo",
#             })
#         print("[DB] Seeded 60 demo records")
"""
ViolaWatch Database Manager
Priority: PostgreSQL (Supabase) → SQLite fallback
Set DATABASE_URL env var for PostgreSQL.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import List, Dict, Optional


class DatabaseManager:

    def __init__(self):
        self._use_pg = False
        self._pg_url = os.environ.get("DATABASE_URL", "")
        if self._pg_url:
            self._init_pg()
        else:
            self._init_sqlite()

    # ── INIT ──────────────────────────────────────────────────────────────

    def _init_pg(self):
        try:
            import psycopg2
            conn = psycopg2.connect(self._pg_url)
            conn.autocommit = True
            c = conn.cursor()
            self._pg_create_tables(c)
            conn.close()
            self._use_pg = True
            print("[DB] PostgreSQL connected (Supabase)")
        except Exception as e:
            print(f"[DB] PostgreSQL failed: {e} → falling back to SQLite")
            self._init_sqlite()

    def _init_sqlite(self):
        import sqlite3
        from pathlib import Path
        self._sqlite_path = str(Path(__file__).parent.parent / "violawatch.db")
        self._use_pg = False
        conn = sqlite3.connect(self._sqlite_path)
        self._sqlite_create_tables(conn)
        conn.close()
        print(f"[DB] SQLite active: {self._sqlite_path}")

    def _get_conn(self):
        if self._use_pg:
            import psycopg2, psycopg2.extras
            conn = psycopg2.connect(self._pg_url)
            conn.autocommit = False
            return conn, False
        else:
            import sqlite3
            conn = sqlite3.connect(self._sqlite_path)
            conn.row_factory = sqlite3.Row
            return conn, True

    def _ph(self, is_sqlite):
        return "?" if is_sqlite else "%s"

    # ── SCHEMA ────────────────────────────────────────────────────────────

    def _pg_create_tables(self, c):
        c.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id             SERIAL PRIMARY KEY,
                timestamp      TIMESTAMP NOT NULL,
                violation_type VARCHAR(50) NOT NULL,
                plate_number   VARCHAR(20) DEFAULT 'UNKNOWN',
                confidence     FLOAT DEFAULT 0.0,
                snapshot_path  TEXT,
                location       VARCHAR(100) DEFAULT 'Camera 1',
                source_type    VARCHAR(20) DEFAULT 'live',
                status         VARCHAR(20) DEFAULT 'pending',
                notes          TEXT,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS video_jobs (
                id               SERIAL PRIMARY KEY,
                filename         VARCHAR(255) NOT NULL,
                status           VARCHAR(20) DEFAULT 'queued',
                total_frames     INT DEFAULT 0,
                processed        INT DEFAULT 0,
                violations_found INT DEFAULT 0,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at     TIMESTAMP,
                error_msg        TEXT
            )
        """)
        # Indexes (ignore if exist)
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_ts ON violations(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_plate ON violations(plate_number)",
            "CREATE INDEX IF NOT EXISTS idx_type ON violations(violation_type)",
        ]:
            try: c.execute(idx)
            except: pass

    def _sqlite_create_tables(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                violation_type TEXT NOT NULL,
                plate_number TEXT DEFAULT 'UNKNOWN',
                confidence REAL DEFAULT 0.0,
                snapshot_path TEXT,
                location TEXT DEFAULT 'Camera 1',
                source_type TEXT DEFAULT 'live',
                status TEXT DEFAULT 'pending',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS video_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                status TEXT DEFAULT 'queued',
                total_frames INTEGER DEFAULT 0,
                processed INTEGER DEFAULT 0,
                violations_found INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                error_msg TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ts ON violations(timestamp);
            CREATE INDEX IF NOT EXISTS idx_plate ON violations(plate_number);
        """)
        conn.commit()

    # ── VIOLATIONS CRUD ───────────────────────────────────────────────────

    def insert_violation(self, data: dict) -> int:
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            c.execute(f"""
                INSERT INTO violations
                    (timestamp,violation_type,plate_number,confidence,snapshot_path,location,source_type)
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """, (
                str(data.get("timestamp", datetime.now())),
                data["violation_type"],
                data.get("plate_number", "UNKNOWN"),
                data.get("confidence", 0.0),
                data.get("snapshot_path", ""),
                data.get("location", "Camera 1"),
                data.get("source_type", "live"),
            ))
            if is_sqlite:
                conn.commit()
                rid = c.lastrowid
            else:
                c.execute("SELECT lastval()")
                rid = c.fetchone()[0]
                conn.commit()
            return rid
        finally:
            conn.close()

    def get_violations(self, limit=25, offset=0, violation_type=None,
                       plate=None, date_from=None, date_to=None,
                       source_type=None) -> List[Dict]:
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            q = "SELECT * FROM violations WHERE 1=1"
            params = []
            if violation_type:
                q += f" AND violation_type={ph}"; params.append(violation_type)
            if plate:
                q += f" AND plate_number LIKE {ph}"; params.append(f"%{plate}%")
            if date_from:
                q += f" AND timestamp>={ph}"; params.append(date_from)
            if date_to:
                q += f" AND timestamp<={ph}"; params.append(date_to)
            if source_type:
                q += f" AND source_type={ph}"; params.append(source_type)
            q += f" ORDER BY timestamp DESC LIMIT {ph} OFFSET {ph}"
            params += [limit, offset]
            c.execute(q, params)
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, row)) for row in c.fetchall()]
        finally:
            conn.close()

    def get_violation_by_id(self, vid: int) -> Optional[Dict]:
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            c.execute(f"SELECT * FROM violations WHERE id={ph}", (vid,))
            cols = [d[0] for d in c.description]
            row = c.fetchone()
            return dict(zip(cols, row)) if row else None
        finally:
            conn.close()

    def count_violations(self, violation_type=None, plate=None) -> int:
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            q = "SELECT COUNT(*) FROM violations WHERE 1=1"
            params = []
            if violation_type:
                q += f" AND violation_type={ph}"; params.append(violation_type)
            if plate:
                q += f" AND plate_number LIKE {ph}"; params.append(f"%{plate}%")
            c.execute(q, params)
            return c.fetchone()[0]
        finally:
            conn.close()

    def update_violation(self, vid: int, status: str, notes: str = None):
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            c.execute(f"UPDATE violations SET status={ph}, notes={ph} WHERE id={ph}",
                      (status, notes, vid))
            conn.commit()
        finally:
            conn.close()

    def delete_violation(self, vid: int):
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            c.execute(f"DELETE FROM violations WHERE id={ph}", (vid,))
            conn.commit()
        finally:
            conn.close()

    def delete_all_violations(self):
        conn, is_sqlite = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM violations")
            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> Dict:
        conn, is_sqlite = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM violations")
            total = c.fetchone()[0]

            if is_sqlite:
                c.execute("SELECT COUNT(*) FROM violations WHERE date(timestamp)=date('now')")
            else:
                c.execute("SELECT COUNT(*) FROM violations WHERE timestamp::date=CURRENT_DATE")
            today = c.fetchone()[0]

            c.execute("SELECT violation_type, COUNT(*) FROM violations GROUP BY violation_type")
            by_type = dict(c.fetchall())

            if is_sqlite:
                c.execute("""
                    SELECT date(timestamp) as day, COUNT(*) as cnt FROM violations
                    WHERE timestamp >= date('now','-6 days') GROUP BY day ORDER BY day
                """)
            else:
                c.execute("""
                    SELECT DATE(timestamp) as day, COUNT(*) as cnt FROM violations
                    WHERE timestamp >= NOW() - INTERVAL '6 days'
                    GROUP BY day ORDER BY day
                """)
            trend = [{"day": str(r[0]), "count": r[1]} for r in c.fetchall()]

            c.execute("SELECT * FROM violations ORDER BY timestamp DESC LIMIT 5")
            cols = [d[0] for d in c.description]
            recent = [dict(zip(cols, r)) for r in c.fetchall()]

            return {"total": total, "today": today, "by_type": by_type,
                    "trend": trend, "recent": recent}
        finally:
            conn.close()

    # ── VIDEO JOBS ────────────────────────────────────────────────────────

    def create_job(self, filename: str) -> int:
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            c.execute(f"INSERT INTO video_jobs (filename) VALUES ({ph})", (filename,))
            if is_sqlite:
                conn.commit()
                return c.lastrowid
            else:
                c.execute("SELECT lastval()")
                rid = c.fetchone()[0]
                conn.commit()
                return rid
        finally:
            conn.close()

    def update_job(self, job_id: int, **kwargs):
        if not kwargs: return
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            sets = ", ".join(f"{k}={ph}" for k in kwargs)
            vals = list(kwargs.values()) + [job_id]
            c.execute(f"UPDATE video_jobs SET {sets} WHERE id={ph}", vals)
            conn.commit()
        finally:
            conn.close()

    def get_job(self, job_id: int) -> Optional[Dict]:
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            c.execute(f"SELECT * FROM video_jobs WHERE id={ph}", (job_id,))
            cols = [d[0] for d in c.description]
            row = c.fetchone()
            return dict(zip(cols, row)) if row else None
        finally:
            conn.close()

    def get_all_jobs(self) -> List[Dict]:
        conn, is_sqlite = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM video_jobs ORDER BY created_at DESC LIMIT 20")
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, r)) for r in c.fetchall()]
        finally:
            conn.close()

    def delete_job(self, job_id: int):
        conn, is_sqlite = self._get_conn()
        ph = self._ph(is_sqlite)
        try:
            c = conn.cursor()
            c.execute(f"DELETE FROM video_jobs WHERE id={ph}", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def seed_demo(self):
        import random
        plates = ["MH12AB1234","KA05MJ5678","DL3CAF4449","TN09AZ1122","UP32GH9900","UNKNOWN"]
        locs   = ["Junction A - Cam1","Highway Exit - Cam3","School Zone - Cam2"]
        for i in range(60):
            dt = datetime.now() - timedelta(
                days=random.randint(0,6),
                hours=random.randint(0,23),
                minutes=random.randint(0,59))
            self.insert_violation({
                "timestamp": dt, "violation_type": "no_helmet",
                "plate_number": random.choice(plates),
                "confidence": round(random.uniform(0.6, 0.97), 2),
                "location": random.choice(locs), "source_type": "demo",
            })
        print("[DB] Seeded 60 demo records")