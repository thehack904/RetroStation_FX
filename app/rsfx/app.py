from __future__ import annotations

import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from . import __version__
from .config import settings
from .database import Database, sanitize_diagnostic_error
from .ersatztv import delete_yaml, sync_yaml
from .ersatztv_refresh import GraphicsRefreshError, request_graphics_refresh, discover_channels, manual_command_info
from .ersatztv_restart import detect_ersatztv_start
from .models import RenderRequest, Style, StylePut, UserTemplate, UserTemplatePut
from .normalize import normalize_context
from .renderer import render_boundary_packet_stream, render_packet_stream
from .timeline import build_position_timeline, plan_position_trigger
from .templates import get_template, list_templates
from .trigger import claim_position_schedule, evaluate_trigger

logger=logging.getLogger("rsfx.runtime")
db=Database(settings.database_path,retain_raw_context=settings.retain_raw_context)
@asynccontextmanager
async def lifespan(app): db.initialize(); yield
app=FastAPI(title='RetroStation FX',version=__version__,lifespan=lifespan)
static_dir=Path(__file__).parent/'static'; app.mount('/static',StaticFiles(directory=static_dir),name='static')
@app.get('/',response_class=HTMLResponse)
def home(): return (static_dir/'index.html').read_text(encoding='utf-8')
@app.get('/v1/health')
def health(): return {'ok':True,'version':__version__,'packet_mode':True}
@app.get('/v1/capabilities')
def capabilities(): return {'product':'RetroStation FX','version':__version__,'api_versions':['v1'],'graphics':{'packet_v1':True,'raw_mode':False,'pixel_format':'bgra','ersatztv_owned_composition':True,'ersatztv_owned_encoding':True,'dynamic_frame_rate':True,'epg_now_next_source':'legacy-template-variables','epg_entries_required':2},'style_management':{'persistent':True,'database':'sqlite','reusable':True,'channel_independent':True,'managed_ersatztv_yaml':True,'duplicate_detection':True,'builtin_templates':True},'integration':{'graphics_logic_owner':'rsfx','shared_style_yaml':True,'runtime_channel_context':False,'runtime_session_context':True,'ersatztv_api_required':False,'schedule_assignment_owner':'ersatztv','deco_assignment_required':False,'graphics_refresh':'best-effort-hls-session','ersatztv_api_key_required':False}}
@app.get('/v1/integration/ersatztv/restart-state')
def ersatztv_restart_state():
    # Compatibility endpoint for older clients. A restart is not required
    # for the supported HLS-triggered synchronization workflow.
    return {
        'yaml_changed_at': db.get_integration_state('ersatztv_yaml_changed_at'),
        'restart_required': False,
        'state': 'manual-sync',
        'message': 'Use Save + Sync to request ErsatzTV graphics registration.',
    }
@app.get('/v1/templates')
def templates(): return list_templates()
@app.get('/v1/templates/{template_id}')
def template(template_id:str):
    item=get_template(template_id)
    if item is None:raise HTTPException(404,'template not found')
    return item
@app.get(
    '/v1/user-templates',
    response_model=list[UserTemplate],
)
def list_user_templates():
    return db.list_user_templates()


@app.get(
    '/v1/user-templates/{template_id}',
    response_model=UserTemplate,
)
def get_user_template(template_id:int):
    item=db.get_user_template(template_id)

    if item is None:
        raise HTTPException(
            404,
            'user template not found',
        )

    return item


@app.post(
    '/v1/user-templates',
    response_model=UserTemplate,
)
def create_user_template(value:UserTemplatePut):
    # Database only by design.
    #
    # Never call sync_yaml() or mark_yaml_changed() from the
    # user-template lifecycle.
    return db.put_user_template(value)


@app.put(
    '/v1/user-templates/{template_id}',
    response_model=UserTemplate,
)
def update_user_template(
    template_id:int,
    value:UserTemplatePut,
):
    if db.get_user_template(template_id) is None:
        raise HTTPException(
            404,
            'user template not found',
        )

    return db.put_user_template(
        value,
        template_id=template_id,
    )


@app.delete('/v1/user-templates/{template_id}')
def remove_user_template(template_id:int):
    if db.get_user_template(template_id) is None:
        raise HTTPException(
            404,
            'user template not found',
        )

    db.delete_user_template(template_id)

    return {
        'deleted': True,
        'id': template_id,
        'ersatztv_restart_required': False,
    }


@app.get('/v1/styles',response_model=list[Style])
def list_styles(): return db.list_styles()
@app.post('/v1/styles/match')
def match_style(value:StylePut):
    match=db.find_matching_style(value)
    return {'match':match.model_dump() if match else None,'generated_name':value.generated_description,'generated_slug':value.generated_slug}
@app.post('/v1/styles',response_model=Style)
def create_style(value:StylePut):
    if not value.name:
        match=db.find_matching_style(value)
        if match:return match
    style=db.put_style(value)
    try:
        path=sync_yaml(style); db.set_style_yaml_path(style.id,str(path) if path else None)
        if path:db.mark_yaml_changed()
    except Exception as exc: raise HTTPException(500,f'style saved but YAML sync failed: {exc}')
    return db.get_style(style.id)
@app.get('/v1/styles/{style_id}',response_model=Style)
def get_style(style_id:int):
    s=db.get_style(style_id)
    if s is None:raise HTTPException(404,'style not found')
    return s
@app.put('/v1/styles/{style_id}',response_model=Style)
def update_style(style_id:int,value:StylePut):
    if db.get_style(style_id) is None:raise HTTPException(404,'style not found')
    s=db.put_style(value,style_id=style_id)
    try:
        path=sync_yaml(s); db.set_style_yaml_path(s.id,str(path) if path else None)
        if path:db.mark_yaml_changed()
    except Exception as exc:raise HTTPException(500,f'style saved but YAML sync failed: {exc}')
    return db.get_style(s.id)
@app.delete('/v1/styles/{style_id}')
def remove_style(style_id:int):
    s=db.get_style(style_id)
    if s is None:raise HTTPException(404,'style not found')
    delete_yaml(s); db.delete_style(style_id)
    if s.manage_ersatztv_yaml:db.mark_yaml_changed()
    return {'deleted':True,'id':style_id,'ersatztv_restart_required':bool(s.manage_ersatztv_yaml)}
@app.post('/v1/styles/{style_id}/sync-ersatztv')
def sync_style(style_id:int):
    s=db.get_style(style_id)
    if s is None:raise HTTPException(404,'style not found')
    p=sync_yaml(s); db.set_style_yaml_path(style_id,str(p) if p else None)
    if p:db.mark_yaml_changed()
    return {'ok':True,'path':str(p) if p else None,'ersatztv_restart_required':bool(p)}
@app.post('/v1/styles/{style_id}/refresh-ersatztv')
def refresh_style_graphics(style_id: int, payload: dict | None = None):
    style = db.get_style(style_id)
    if style is None:
        raise HTTPException(404, 'style not found')
    if not style.manage_ersatztv_yaml or not style.yaml_path or not Path(style.yaml_path).is_file():
        raise HTTPException(409, 'Save the managed ErsatzTV YAML before syncing')
    return _request_ersatztv_sync(payload)


# RSFX_CHANNEL_DROPDOWN_MANUAL_V1
@app.get('/v1/integration/ersatztv/channels')
def ersatztv_channel_choices():
    try:
        result = discover_channels()
        return {'channels': result['channels']}
    except GraphicsRefreshError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get('/v1/integration/ersatztv/manual-sync')
def ersatztv_manual_sync(channel: str = ''):
    try:
        return manual_command_info(channel)
    except GraphicsRefreshError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post('/v1/integration/ersatztv/refresh-after-delete')
def refresh_graphics_after_delete(payload: dict | None = None):
    # Independent route: the deleted style MUST NOT be re-created or saved.
    return _request_ersatztv_sync(payload)


def _request_ersatztv_sync(payload: dict | None) -> dict:
    try:
        return request_graphics_refresh(str((payload or {}).get('channel') or ''))
    except GraphicsRefreshError as exc:
        logger.warning('ErsatzTV graphics refresh attempt failed: %s', type(exc).__name__)
        raise HTTPException(502, str(exc)) from exc


@app.post('/v1/render/packet')
def render_packet(req:RenderRequest):
    seen=time.time(); style=db.get_style(req.style_id)
    if style is None:return Response(status_code=204)

    channel_id=(req.channel_id or '').strip()
    context=req.context if isinstance(req.context,dict) else {}
    session_key=str(context.get('Channel_StartTime') or '').strip()

    if not session_key and not channel_id:
        logger.warning("render suppressed: missing runtime session context style_id=%s context_keys=%s", style.id, sorted(context.keys()))
        return Response(status_code=204,headers={'X-RSFX-Style-ID':str(style.id),'X-RSFX-Trigger':'suppressed','X-RSFX-Trigger-Reason':'missing-runtime-session-context'})

    if session_key:
        state_key=f"style:{style.id}|channel:{channel_id}|session:{session_key}"
    else:
        state_key=f"style:{style.id}|channel:{channel_id}"

    runtime_name=(req.channel_name or '').strip()
    if not runtime_name:
        runtime_name=str(context.get('MediaItem_ShowTitle') or '').strip()
    if not runtime_name:
        epg=context.get('Epg') or []
        if epg and isinstance(epg[0],dict):
            runtime_name=str(epg[0].get('Title') or '').strip()
    if not runtime_name:
        runtime_name=channel_id or style.display_name

    try:
        n=normalize_context(channel_id,runtime_name,context)
        db.record_runtime_context(state_key,style.id,channel_id,n.session_key,runtime_name,context,n.model_dump(),n.fps,n.width,n.height,seen)

        decision=evaluate_trigger(db,style,n,state_key)
        state=db.get_runtime_trigger_state(state_key)
        plan=plan_position_trigger(style,n,state)
        db.record_runtime_timeline_plan(state_key,style.id,channel_id,n.session_key,runtime_name,plan.to_dict())

        if plan.scheduled:
            timeline=build_position_timeline(style,n,decision.show,plan,decision.reason)
            claim_position_schedule(db,state_key,style.id,channel_id,timeline.schedule_reason)
            db.record_runtime_render(state_key,style.id,channel_id,n.session_key,runtime_name,context,n.model_dump(),'packet-v1-timeline',n.fps,n.width,n.height,seen)
            return Response(content=timeline.payload,media_type='application/octet-stream',headers={'X-RSFX-Packet':'v1','X-RSFX-Style-ID':str(style.id),'X-RSFX-Timeline':'position','X-RSFX-Trigger':'show' if decision.show else 'scheduled','X-RSFX-Trigger-Reason':decision.reason if decision.show else timeline.schedule_reason,'X-RSFX-Position-Status':plan.status,'X-RSFX-FPS':f'{n.fps:g}','X-RSFX-Frames':str(timeline.total_frames),'X-RSFX-Region':','.join(map(str,timeline.region))})

        if not decision.show:
            return Response(status_code=204,headers={'X-RSFX-Style-ID':str(style.id),'X-RSFX-Trigger':'suppressed','X-RSFX-Trigger-Reason':decision.reason,'X-RSFX-Position-Status':plan.status})

        payload,stats,tune_delay_frames=render_boundary_packet_stream(style,n,decision.reason)
        db.record_runtime_render(state_key,style.id,channel_id,n.session_key,runtime_name,context,n.model_dump(),'packet-v1',n.fps,n.width,n.height,seen)
        return Response(content=payload,media_type='application/octet-stream',headers={'X-RSFX-Packet':'v1','X-RSFX-Style-ID':str(style.id),'X-RSFX-FPS':f'{n.fps:g}','X-RSFX-Frames':str(stats.frames),'X-RSFX-Region':','.join(map(str,stats.region)),'X-RSFX-Trigger':'show','X-RSFX-Trigger-Reason':decision.reason,'X-RSFX-Tune-Delay':f'{style.trigger_policy.tune_delay_seconds:g}' if decision.reason=='channel-tune' else '0','X-RSFX-Tune-Delay-Frames':str(tune_delay_frames),'X-RSFX-Position-Status':plan.status})
    except Exception as exc:
        db.record_runtime_error(state_key,style.id,channel_id,session_key,runtime_name,exc,seen)
        raise HTTPException(500,f'render failed: {sanitize_diagnostic_error(exc)}')
