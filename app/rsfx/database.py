from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Appearance, Channel, ChannelPut, Eligibility, Style, StylePut, TriggerPolicy, UserTemplate, UserTemplatePut

SCHEMA = '''
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY,name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS styles (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,slug TEXT NOT NULL UNIQUE,manage_ersatztv_yaml INTEGER NOT NULL DEFAULT 1,overlay_display_seconds REAL NOT NULL DEFAULT 7.0,eligibility_start_seconds REAL NOT NULL DEFAULT 0.0,eligibility_duration_seconds REAL NOT NULL DEFAULT 21600.0,trigger_json TEXT NOT NULL,appearance_json TEXT NOT NULL,z_index INTEGER NOT NULL DEFAULT 20,yaml_path TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_templates (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,slug TEXT NOT NULL UNIQUE,description TEXT,source_kind TEXT,source_template_id TEXT,source_template_name TEXT,style_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS style_channel_assignments (style_id INTEGER NOT NULL REFERENCES styles(id) ON DELETE CASCADE,channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,created_at TEXT NOT NULL,PRIMARY KEY(style_id,channel_id));
CREATE TABLE IF NOT EXISTS channel_diagnostics (channel_id TEXT PRIMARY KEY REFERENCES channels(id) ON DELETE CASCADE,last_context_json TEXT,last_normalized_json TEXT,last_error TEXT,last_adapter_seen REAL,renders INTEGER NOT NULL DEFAULT 0,last_render_format TEXT,last_fps REAL,last_width INTEGER,last_height INTEGER,last_timeline_json TEXT,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS channel_trigger_state (channel_id TEXT PRIMARY KEY REFERENCES channels(id) ON DELETE CASCADE,session_key TEXT,program_key TEXT,last_elapsed_percent REAL,fired_tune INTEGER NOT NULL DEFAULT 0,fired_program_change INTEGER NOT NULL DEFAULT 0,fired_position INTEGER NOT NULL DEFAULT 0,last_decision TEXT,last_reason TEXT,updated_at TEXT NOT NULL);\nCREATE TABLE IF NOT EXISTS runtime_trigger_state (state_key TEXT PRIMARY KEY,style_id INTEGER NOT NULL REFERENCES styles(id) ON DELETE CASCADE,channel_id TEXT,session_key TEXT,program_key TEXT,last_elapsed_percent REAL,fired_tune INTEGER NOT NULL DEFAULT 0,fired_program_change INTEGER NOT NULL DEFAULT 0,fired_position INTEGER NOT NULL DEFAULT 0,last_decision TEXT,last_reason TEXT,updated_at TEXT NOT NULL);\nCREATE TABLE IF NOT EXISTS runtime_diagnostics (state_key TEXT PRIMARY KEY,style_id INTEGER NOT NULL REFERENCES styles(id) ON DELETE CASCADE,channel_id TEXT,session_key TEXT,runtime_name TEXT,last_context_json TEXT,last_normalized_json TEXT,last_error TEXT,last_adapter_seen REAL,renders INTEGER NOT NULL DEFAULT 0,last_render_format TEXT,last_fps REAL,last_width INTEGER,last_height INTEGER,last_timeline_json TEXT,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS integration_state (key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_channels_enabled ON channels(enabled);
CREATE INDEX IF NOT EXISTS idx_style_assignments_channel ON style_channel_assignments(channel_id);\nCREATE INDEX IF NOT EXISTS idx_runtime_trigger_style ON runtime_trigger_state(style_id);\nCREATE INDEX IF NOT EXISTS idx_runtime_diagnostics_style ON runtime_diagnostics(style_id);
'''

def utc_now(): return datetime.now(timezone.utc).isoformat()

RUNTIME_DIAGNOSTIC_RETENTION_DAYS = 30
RUNTIME_DIAGNOSTIC_MAX_ROWS = 1000
_SENSITIVE_FIELD = re.compile(
    r"password|passwd|token|secret|credential|authorization|cookie|"
    r"(?:api|access|private)[_-]?key",
    re.IGNORECASE,
)
_SENSITIVE_ERROR = re.compile(
    r"(\b(?:password|passwd|token|secret|credential|authorization|cookie|"
    r"(?:api|access|private)[_-]?key)\b\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\r\n,;}\]]*)",
    re.IGNORECASE,
)
_URL_CREDENTIALS = re.compile(r"(?i)(https?://)[^/@\s]+@")
_BEARER_CREDENTIAL = re.compile(r"(?i)\bBearer\s+\S+")


def _redact_context(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE_FIELD.search(str(key)) else _redact_context(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_context(item) for item in value]
    return value


def diagnostic_context(context, retain_raw=False):
    context = context if isinstance(context, dict) else {}
    if retain_raw:
        return _redact_context(context)

    fields = (
        "FrameRate",
        "RFrameRate",
        "Channel_StartTime",
        "MediaItem_ShowTitle",
        "MediaItem_Title",
        "MediaItem_Start",
        "MediaItem_Stop",
        "MediaItem_StreamSeek",
        "MediaItem_Duration",
    )
    result = {key: context[key] for key in fields if key in context}
    for key in ("ScaledResolution", "Resolution"):
        block = context.get(key)
        if isinstance(block, dict):
            result[key] = {
                dimension: block[dimension]
                for dimension in ("Width", "Height")
                if dimension in block
            }
    epg = context.get("Epg")
    if isinstance(epg, list):
        result["Epg"] = [
            {
                key: entry[key]
                for key in ("Title", "SubTitle", "Start", "Stop")
                if key in entry
            }
            for entry in epg[:2]
            if isinstance(entry, dict)
        ]
    return _redact_context(result)


def diagnostic_normalized(normalized):
    if hasattr(normalized, "model_dump"):
        normalized = normalized.model_dump()
    if not isinstance(normalized, dict):
        return normalized
    result = dict(normalized)
    result.pop("media_path", None)
    result.pop("program_key", None)
    return _redact_context(result)


def sanitize_diagnostic_error(error):
    message = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", str(error))
    message = _BEARER_CREDENTIAL.sub("******", message)
    return _SENSITIVE_ERROR.sub(r"\1[REDACTED]", message)[:4000]


class Database:
    def __init__(self,path:Path,retain_raw_context=False):
        self.path=path
        self.retain_raw_context=retain_raw_context
    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(self.path,timeout=30); c.row_factory=sqlite3.Row
        try: c.executescript(SCHEMA); yield c; c.commit()
        finally: c.close()
    def initialize(self):
        with self.connect() as c:
            self._sanitize_existing_diagnostics(c)

    def _sanitize_existing_diagnostics(self,c):
        for table, key in (
            ("runtime_diagnostics", "state_key"),
            ("channel_diagnostics", "channel_id"),
        ):
            rows=c.execute(
                f"SELECT {key},last_context_json,last_normalized_json,last_error FROM {table} "
                "WHERE last_context_json IS NOT NULL OR last_normalized_json IS NOT NULL "
                "OR last_error IS NOT NULL"
            ).fetchall()
            for row in rows:
                context=None
                normalized=None
                if row["last_context_json"]:
                    try:
                        context=diagnostic_context(
                            json.loads(row["last_context_json"]),
                            self.retain_raw_context,
                        )
                    except (TypeError, ValueError):
                        context=None
                if row["last_normalized_json"]:
                    try:
                        normalized=diagnostic_normalized(
                            json.loads(row["last_normalized_json"])
                        )
                    except (TypeError, ValueError):
                        normalized=None
                c.execute(
                    f"UPDATE {table} SET last_context_json=?,last_normalized_json=?,last_error=? "
                    f"WHERE {key}=?",
                    (
                        json.dumps(context,separators=(",",":")) if context is not None else None,
                        json.dumps(normalized,separators=(",",":")) if normalized is not None else None,
                        sanitize_diagnostic_error(row["last_error"]) if row["last_error"] is not None else None,
                        row[key],
                    ),
                )

    def _prune_runtime_diagnostics(self,c,now):
        cutoff=(datetime.fromisoformat(now)-timedelta(days=RUNTIME_DIAGNOSTIC_RETENTION_DAYS)).isoformat()
        c.execute("DELETE FROM runtime_diagnostics WHERE updated_at < ?",(cutoff,))
        c.execute(
            "DELETE FROM runtime_diagnostics WHERE state_key NOT IN "
            "(SELECT state_key FROM runtime_diagnostics "
            "ORDER BY updated_at DESC,state_key DESC LIMIT ?)",
            (RUNTIME_DIAGNOSTIC_MAX_ROWS,),
        )
    def _style(self,r):
        return Style(id=r['id'],name=r['name'],slug=r['slug'],manage_ersatztv_yaml=bool(r['manage_ersatztv_yaml']),overlay_display_seconds=r['overlay_display_seconds'],eligibility=Eligibility(start_seconds=r['eligibility_start_seconds'],duration_seconds=r['eligibility_duration_seconds']),trigger_policy=TriggerPolicy.model_validate_json(r['trigger_json']),appearance=Appearance.model_validate_json(r['appearance_json']),z_index=r['z_index'],yaml_path=r['yaml_path'],created_at=r['created_at'],updated_at=r['updated_at'])
    def _user_template(self,r):
        return UserTemplate(
            id=r['id'],
            name=r['name'],
            slug=r['slug'],
            description=r['description'],
            source_kind=r['source_kind'],
            source_template_id=r['source_template_id'],
            source_template_name=r['source_template_name'],
            style=StylePut.model_validate_json(r['style_json']),
            created_at=r['created_at'],
            updated_at=r['updated_at'],
        )

    def list_user_templates(self):
        with self.connect() as c:
            rows=c.execute(
                'SELECT * FROM user_templates ORDER BY id'
            ).fetchall()

        return [
            self._user_template(r)
            for r in rows
        ]

    def get_user_template(self,i):
        with self.connect() as c:
            r=c.execute(
                'SELECT * FROM user_templates WHERE id=?',
                (i,),
            ).fetchone()

        return (
            self._user_template(r)
            if r
            else None
        )

    def put_user_template(
        self,
        value:UserTemplatePut,
        template_id=None,
    ):
        now=utc_now()

        old=(
            self.get_user_template(template_id)
            if template_id is not None
            else None
        )

        created=(
            old.created_at
            if old
            else now
        )

        # Persistent identity and filesystem-safe naming are
        # intentionally separate from the display name.
        slug=(
            old.slug
            if old
            else value.style.generated_slug
        )

        if not old:
            from .models import style_slug

            slug=style_slug(value.name)

        with self.connect() as c:
            if old:
                c.execute(
                    'UPDATE user_templates '
                    'SET name=?,description=?,source_kind=?,'
                    'source_template_id=?,source_template_name=?,'
                    'style_json=?,updated_at=? '
                    'WHERE id=?',
                    (
                        value.name,
                        value.description,
                        value.source_kind,
                        value.source_template_id,
                        value.source_template_name,
                        value.style.model_dump_json(),
                        now,
                        template_id,
                    ),
                )

                rid=template_id

            else:
                base=slug
                n=2

                while c.execute(
                    'SELECT 1 FROM user_templates WHERE slug=?',
                    (slug,),
                ).fetchone():
                    slug=f'{base}-{n}'
                    n+=1

                cur=c.execute(
                    'INSERT INTO user_templates('
                    'name,slug,description,source_kind,'
                    'source_template_id,source_template_name,'
                    'style_json,created_at,updated_at'
                    ') VALUES(?,?,?,?,?,?,?,?,?)',
                    (
                        value.name,
                        slug,
                        value.description,
                        value.source_kind,
                        value.source_template_id,
                        value.source_template_name,
                        value.style.model_dump_json(),
                        created,
                        now,
                    ),
                )

                rid=cur.lastrowid

        return self.get_user_template(rid)

    def delete_user_template(self,i):
        with self.connect() as c:
            return (
                c.execute(
                    'DELETE FROM user_templates WHERE id=?',
                    (i,),
                ).rowcount
                > 0
            )

    def _channel(self,r,style_ids=None): return Channel(id=r['id'],name=r['name'],enabled=bool(r['enabled']),style_ids=style_ids or [],created_at=r['created_at'],updated_at=r['updated_at'])
    def list_styles(self):
        with self.connect() as c: rows=c.execute('SELECT * FROM styles ORDER BY id').fetchall()
        return [self._style(r) for r in rows]
    def get_style(self,i):
        with self.connect() as c: r=c.execute('SELECT * FROM styles WHERE id=?',(i,)).fetchone()
        return self._style(r) if r else None
    def find_matching_style(self,v:StylePut):
        if v.name: return None
        target=(v.manage_ersatztv_yaml,v.overlay_display_seconds,v.eligibility.model_dump(),v.trigger_policy.model_dump(),v.appearance.model_dump(),v.z_index)
        for s in self.list_styles():
            current=(s.manage_ersatztv_yaml,s.overlay_display_seconds,s.eligibility.model_dump(),s.trigger_policy.model_dump(),s.appearance.model_dump(),s.z_index)
            if current==target: return s
        return None
    def put_style(self,v:StylePut,style_id=None,yaml_path=None):
        now=utc_now(); old=self.get_style(style_id) if style_id is not None else None; created=old.created_at if old else now; slug=old.slug if old else v.generated_slug
        if yaml_path is None and old: yaml_path=old.yaml_path
        with self.connect() as c:
            if old:
                c.execute('UPDATE styles SET name=?,manage_ersatztv_yaml=?,overlay_display_seconds=?,eligibility_start_seconds=?,eligibility_duration_seconds=?,trigger_json=?,appearance_json=?,z_index=?,yaml_path=?,updated_at=? WHERE id=?',(v.name,int(v.manage_ersatztv_yaml),v.overlay_display_seconds,v.eligibility.start_seconds,v.eligibility.duration_seconds,v.trigger_policy.model_dump_json(),v.appearance.model_dump_json(),v.z_index,yaml_path,now,style_id)); rid=style_id
            else:
                base=slug; n=2
                while c.execute('SELECT 1 FROM styles WHERE slug=?',(slug,)).fetchone(): slug=f'{base}-{n}'; n+=1
                cur=c.execute('INSERT INTO styles(name,slug,manage_ersatztv_yaml,overlay_display_seconds,eligibility_start_seconds,eligibility_duration_seconds,trigger_json,appearance_json,z_index,yaml_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(v.name,slug,int(v.manage_ersatztv_yaml),v.overlay_display_seconds,v.eligibility.start_seconds,v.eligibility.duration_seconds,v.trigger_policy.model_dump_json(),v.appearance.model_dump_json(),v.z_index,yaml_path,created,now)); rid=cur.lastrowid
        return self.get_style(rid)
    def set_style_yaml_path(self,i,path):
        with self.connect() as c: c.execute('UPDATE styles SET yaml_path=?,updated_at=? WHERE id=?',(path,utc_now(),i))
    def mark_yaml_changed(self):
        now=utc_now()
        with self.connect() as c:c.execute("INSERT INTO integration_state(key,value,updated_at) VALUES('ersatztv_yaml_changed_at',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(now,now))
        return now
    def get_integration_state(self,key):
        with self.connect() as c:r=c.execute('SELECT value FROM integration_state WHERE key=?',(key,)).fetchone()
        return r['value'] if r else None
    def delete_style(self,i):
        with self.connect() as c: return c.execute('DELETE FROM styles WHERE id=?',(i,)).rowcount>0
    def list_channels(self):
        with self.connect() as c:
            rows=c.execute('SELECT * FROM channels ORDER BY id').fetchall(); aa=c.execute('SELECT channel_id,style_id FROM style_channel_assignments ORDER BY style_id').fetchall()
        m={}
        for a in aa: m.setdefault(a['channel_id'],[]).append(a['style_id'])
        return [self._channel(r,m.get(r['id'],[])) for r in rows]
    def get_channel(self,i):
        with self.connect() as c:
            r=c.execute('SELECT * FROM channels WHERE id=?',(i,)).fetchone()
            if not r:return None
            ids=[x['style_id'] for x in c.execute('SELECT style_id FROM style_channel_assignments WHERE channel_id=? ORDER BY style_id',(i,)).fetchall()]
        return self._channel(r,ids)
    def put_channel(self,i,v:ChannelPut):
        now=utc_now(); old=self.get_channel(i); created=old.created_at if old else now
        with self.connect() as c:
            c.execute('INSERT INTO channels(id,name,enabled,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,enabled=excluded.enabled,updated_at=excluded.updated_at',(i,v.name,int(v.enabled),created,now)); c.execute('INSERT INTO channel_diagnostics(channel_id,updated_at) VALUES(?,?) ON CONFLICT(channel_id) DO NOTHING',(i,now))
        return self.get_channel(i)
    def delete_channel(self,i):
        with self.connect() as c:return c.execute('DELETE FROM channels WHERE id=?',(i,)).rowcount>0
    def assign_style(self,s,cid):
        if self.get_style(s) is None or self.get_channel(cid) is None:return False
        with self.connect() as c:c.execute('INSERT INTO style_channel_assignments(style_id,channel_id,created_at) VALUES(?,?,?) ON CONFLICT(style_id,channel_id) DO NOTHING',(s,cid,utc_now()))
        return True
    def unassign_style(self,s,cid):
        with self.connect() as c:return c.execute('DELETE FROM style_channel_assignments WHERE style_id=? AND channel_id=?',(s,cid)).rowcount>0
    def channels_for_style(self,s):
        with self.connect() as c:rows=c.execute('SELECT c.* FROM channels c JOIN style_channel_assignments a ON a.channel_id=c.id WHERE a.style_id=? ORDER BY c.id',(s,)).fetchall()
        return [self._channel(r,[s]) for r in rows]
    def styles_for_channel(self,cid):
        with self.connect() as c:rows=c.execute('SELECT s.* FROM styles s JOIN style_channel_assignments a ON a.style_id=s.id WHERE a.channel_id=? ORDER BY s.id',(cid,)).fetchall()
        return [self._style(r) for r in rows]
    def record_context(self,cid,context,normalized,fps,width,height,seen):
        with self.connect() as c:c.execute('INSERT INTO channel_diagnostics(channel_id,last_context_json,last_normalized_json,last_adapter_seen,renders,last_fps,last_width,last_height,updated_at) VALUES(?,?,?,?,0,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET last_context_json=excluded.last_context_json,last_normalized_json=excluded.last_normalized_json,last_adapter_seen=excluded.last_adapter_seen,last_fps=excluded.last_fps,last_width=excluded.last_width,last_height=excluded.last_height,updated_at=excluded.updated_at',(cid,json.dumps(diagnostic_context(context,self.retain_raw_context),separators=(",",":")),json.dumps(diagnostic_normalized(normalized),separators=(",",":")),seen,fps,width,height,utc_now()))
    def record_render(self,cid,context,normalized,fmt,fps,width,height,seen):
        with self.connect() as c:c.execute('INSERT INTO channel_diagnostics(channel_id,last_context_json,last_normalized_json,last_error,last_adapter_seen,renders,last_render_format,last_fps,last_width,last_height,updated_at) VALUES(?,?,?,NULL,?,1,?,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET last_context_json=excluded.last_context_json,last_normalized_json=excluded.last_normalized_json,last_error=NULL,last_adapter_seen=excluded.last_adapter_seen,renders=channel_diagnostics.renders+1,last_render_format=excluded.last_render_format,last_fps=excluded.last_fps,last_width=excluded.last_width,last_height=excluded.last_height,updated_at=excluded.updated_at',(cid,json.dumps(diagnostic_context(context,self.retain_raw_context),separators=(",",":")),json.dumps(diagnostic_normalized(normalized),separators=(",",":")),seen,fmt,fps,width,height,utc_now()))
    def record_timeline_plan(self,cid,plan):
        with self.connect() as c:c.execute('INSERT INTO channel_diagnostics(channel_id,last_timeline_json,updated_at) VALUES(?,?,?) ON CONFLICT(channel_id) DO UPDATE SET last_timeline_json=excluded.last_timeline_json,updated_at=excluded.updated_at',(cid,json.dumps(plan,separators=(",",":")),utc_now()))
    def record_error(self,cid,error,seen=None):
        if self.get_channel(cid) is None:return
        with self.connect() as c:c.execute('INSERT INTO channel_diagnostics(channel_id,last_error,last_adapter_seen,updated_at) VALUES(?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET last_error=excluded.last_error,last_adapter_seen=COALESCE(excluded.last_adapter_seen,channel_diagnostics.last_adapter_seen),updated_at=excluded.updated_at',(cid,sanitize_diagnostic_error(error),seen,utc_now()))
    def get_trigger_state(self,cid):
        with self.connect() as c:r=c.execute('SELECT * FROM channel_trigger_state WHERE channel_id=?',(cid,)).fetchone()
        return None if not r else {k:(bool(r[k]) if k in {'fired_tune','fired_program_change','fired_position'} else r[k]) for k in r.keys()}
    def set_trigger_state(self,cid,*,session_key,program_key,last_elapsed_percent,fired_tune,fired_program_change,fired_position,last_decision,last_reason):
        with self.connect() as c:c.execute('INSERT INTO channel_trigger_state(channel_id,session_key,program_key,last_elapsed_percent,fired_tune,fired_program_change,fired_position,last_decision,last_reason,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET session_key=excluded.session_key,program_key=excluded.program_key,last_elapsed_percent=excluded.last_elapsed_percent,fired_tune=excluded.fired_tune,fired_program_change=excluded.fired_program_change,fired_position=excluded.fired_position,last_decision=excluded.last_decision,last_reason=excluded.last_reason,updated_at=excluded.updated_at',(cid,session_key,program_key,last_elapsed_percent,int(fired_tune),int(fired_program_change),int(fired_position),last_decision,last_reason,utc_now()))
    def reset_trigger_state(self,cid):
        with self.connect() as c:c.execute('DELETE FROM channel_trigger_state WHERE channel_id=?',(cid,))
    def get_runtime_trigger_state(self,state_key):
        with self.connect() as c:r=c.execute('SELECT * FROM runtime_trigger_state WHERE state_key=?',(state_key,)).fetchone()
        return None if not r else {k:(bool(r[k]) if k in {'fired_tune','fired_program_change','fired_position'} else r[k]) for k in r.keys()}
    def set_runtime_trigger_state(self,state_key,style_id,channel_id,*,session_key,program_key,last_elapsed_percent,fired_tune,fired_program_change,fired_position,last_decision,last_reason):
        with self.connect() as c:c.execute('INSERT INTO runtime_trigger_state(state_key,style_id,channel_id,session_key,program_key,last_elapsed_percent,fired_tune,fired_program_change,fired_position,last_decision,last_reason,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(state_key) DO UPDATE SET style_id=excluded.style_id,channel_id=excluded.channel_id,session_key=excluded.session_key,program_key=excluded.program_key,last_elapsed_percent=excluded.last_elapsed_percent,fired_tune=excluded.fired_tune,fired_program_change=excluded.fired_program_change,fired_position=excluded.fired_position,last_decision=excluded.last_decision,last_reason=excluded.last_reason,updated_at=excluded.updated_at',(state_key,style_id,channel_id or None,session_key,program_key,last_elapsed_percent,int(fired_tune),int(fired_program_change),int(fired_position),last_decision,last_reason,utc_now()))
    def record_runtime_context(self,state_key,style_id,channel_id,session_key,runtime_name,context,normalized,fps,width,height,seen):
        now=utc_now()
        with self.connect() as c:
            c.execute(
                'INSERT INTO runtime_diagnostics(state_key,style_id,channel_id,session_key,runtime_name,last_context_json,last_normalized_json,last_adapter_seen,renders,last_fps,last_width,last_height,updated_at) VALUES(?,?,?,?,?,?,?,?,0,?,?,?,?) ON CONFLICT(state_key) DO UPDATE SET style_id=excluded.style_id,channel_id=excluded.channel_id,session_key=excluded.session_key,runtime_name=excluded.runtime_name,last_context_json=excluded.last_context_json,last_normalized_json=excluded.last_normalized_json,last_adapter_seen=excluded.last_adapter_seen,last_fps=excluded.last_fps,last_width=excluded.last_width,last_height=excluded.last_height,updated_at=excluded.updated_at',
                (
                    state_key,style_id,channel_id or None,session_key,runtime_name,
                    json.dumps(diagnostic_context(context,self.retain_raw_context),separators=(",",":")),
                    json.dumps(diagnostic_normalized(normalized),separators=(",",":")),
                    seen,fps,width,height,now,
                ),
            )
            self._prune_runtime_diagnostics(c,now)
    def record_runtime_render(self,state_key,style_id,channel_id,session_key,runtime_name,context,normalized,fmt,fps,width,height,seen):
        now=utc_now()
        with self.connect() as c:
            c.execute(
                'INSERT INTO runtime_diagnostics(state_key,style_id,channel_id,session_key,runtime_name,last_context_json,last_normalized_json,last_error,last_adapter_seen,renders,last_render_format,last_fps,last_width,last_height,updated_at) VALUES(?,?,?,?,?,?,?,NULL,?,1,?,?,?,?,?) ON CONFLICT(state_key) DO UPDATE SET style_id=excluded.style_id,channel_id=excluded.channel_id,session_key=excluded.session_key,runtime_name=excluded.runtime_name,last_context_json=excluded.last_context_json,last_normalized_json=excluded.last_normalized_json,last_error=NULL,last_adapter_seen=excluded.last_adapter_seen,renders=runtime_diagnostics.renders+1,last_render_format=excluded.last_render_format,last_fps=excluded.last_fps,last_width=excluded.last_width,last_height=excluded.last_height,updated_at=excluded.updated_at',
                (
                    state_key,style_id,channel_id or None,session_key,runtime_name,
                    json.dumps(diagnostic_context(context,self.retain_raw_context),separators=(",",":")),
                    json.dumps(diagnostic_normalized(normalized),separators=(",",":")),
                    seen,fmt,fps,width,height,now,
                ),
            )
            self._prune_runtime_diagnostics(c,now)
    def record_runtime_timeline_plan(self,state_key,style_id,channel_id,session_key,runtime_name,plan):
        now=utc_now()
        with self.connect() as c:
            c.execute(
                'INSERT INTO runtime_diagnostics(state_key,style_id,channel_id,session_key,runtime_name,last_timeline_json,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(state_key) DO UPDATE SET style_id=excluded.style_id,channel_id=excluded.channel_id,session_key=excluded.session_key,runtime_name=excluded.runtime_name,last_timeline_json=excluded.last_timeline_json,updated_at=excluded.updated_at',
                (state_key,style_id,channel_id or None,session_key,runtime_name,json.dumps(plan,separators=(",",":")),now),
            )
            self._prune_runtime_diagnostics(c,now)
    def record_runtime_error(self,state_key,style_id,channel_id,session_key,runtime_name,error,seen=None):
        now=utc_now()
        with self.connect() as c:
            c.execute(
                'INSERT INTO runtime_diagnostics(state_key,style_id,channel_id,session_key,runtime_name,last_error,last_adapter_seen,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(state_key) DO UPDATE SET style_id=excluded.style_id,channel_id=excluded.channel_id,session_key=excluded.session_key,runtime_name=excluded.runtime_name,last_error=excluded.last_error,last_adapter_seen=COALESCE(excluded.last_adapter_seen,runtime_diagnostics.last_adapter_seen),updated_at=excluded.updated_at',
                (state_key,style_id,channel_id or None,session_key,runtime_name,sanitize_diagnostic_error(error),seen,now),
            )
            self._prune_runtime_diagnostics(c,now)
    def diagnostics(self,cid):
        with self.connect() as c:r=c.execute('SELECT * FROM channel_diagnostics WHERE channel_id=?',(cid,)).fetchone()
        if not r:return None
        result=dict(r)
        for k in ('last_context_json','last_normalized_json','last_timeline_json'):
            raw=result.pop(k,None); result[k.removesuffix('_json')]=json.loads(raw) if raw else None
        return result
