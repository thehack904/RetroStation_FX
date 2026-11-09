from __future__ import annotations

import time
import logging
from io import BytesIO
from PIL import Image
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from . import __version__
from .config import settings
from .database import Database, sanitize_diagnostic_error
from .ersatztv import YamlFilesystemPermissionError, delete_yaml, sync_yaml
from .ersatztv_refresh import GraphicsRefreshError, request_graphics_refresh, discover_channels, manual_command_info
from .ersatztv_restart import detect_ersatztv_start
from .models import RenderRequest, Style, StylePut, UserTemplate, UserTemplatePut
from .normalize import normalize_context
from .holiday import asset_path, select_artwork, host_date
from .renderer import _frame, _region, render_boundary_packet_stream, render_packet_stream
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
@app.get('/v1/holiday/selection')
def holiday_selection(
    theme: str = Query(default='automatic', max_length=32),
    program_key: str = Query(default='preview:holiday-vault', max_length=512),
):
    try:
        season, asset = select_artwork(theme, program_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail='Invalid holiday selection') from exc
    return {'holiday': season, 'asset': asset}


@app.get('/v1/holiday/artwork/{theme}/{asset}')
def holiday_artwork(theme: str, asset: str):
    try:
        path = asset_path(theme, asset)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail='Unknown holiday artwork') from exc
    if not path.is_file():
        raise HTTPException(status_code=503, detail='Bundled artwork is not installed')
    return FileResponse(path, media_type='image/png', headers={
        'Cache-Control': 'public, max-age=86400',
        'X-Content-Type-Options': 'nosniff',
    })


@app.post('/v1/holiday/preview')
def holiday_preview(
    style: StylePut,
    width: int = Query(default=1280, ge=1, le=1280),
    height: int = Query(default=720, ge=1, le=720),
):
    """Pixel-identical still frame from the same Pillow/Packet v1 renderer.

    Does not save a Style, create managed YAML, or contact ErsatzTV.
    """
    if style.appearance.theme != 'holiday-broadcast':
        raise HTTPException(status_code=422, detail='Holiday Broadcast theme required')
    if (width, height) not in {(640, 480), (1280, 720)}:
        raise HTTPException(status_code=422, detail='Unsupported preview resolution')
    season, artwork = select_artwork(
        style.appearance.holiday_theme, 'preview:holiday-vault', today=host_date()
    )
    samples = {
        'thanksgiving': ('Planes, Trains and Automobiles', 'A Charlie Brown Thanksgiving'),
        'christmas': ('White Christmas', 'Miracle on 34th Street'),
        'new-year': ('When Harry Met Sally', 'The Apartment'),
        'neutral': ('The Holiday', 'Home for the Holidays'),
    }
    current, upcoming = samples[season]
    n = normalize_context(
        '', 'HOLIDAY VAULT',
        {'FrameRate': 30, 'Resolution': {'Width': width, 'Height': height},
         'Epg': [{'Title': current, 'Start': 'sample-program-start'},
                 {'Title': upcoming}]},
    )
    region = _region(style, n)
    try:
        buffer = _frame(style, n, 1.0, region, 'none', 'enter', (season, artwork))
        image = Image.frombytes('RGBA', region[2:], buffer, 'raw', 'BGRA')
        output = BytesIO()
        image.save(output, format='PNG')
    except (ValueError, OSError) as exc:
        logger.exception('Holiday preview rendering failed')
        raise HTTPException(status_code=500, detail='Holiday preview rendering failed') from exc
    return Response(output.getvalue(), media_type='image/png', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


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


def _yaml_sync_error(
    exc: Exception,
    *,
    saved: bool,
) -> HTTPException:
    """Return actionable but non-sensitive YAML deployment failures."""
    if isinstance(exc, YamlFilesystemPermissionError):
        message = (
            'YAML deployment blocked by filesystem permissions. '
            'Check RSFX service-account traversal, effective ACL masks, and '
            'write access to the configured ErsatzTV Script Graphics directory; '
            'rerun the RSFX installer/upgrade to repair its scoped ACLs.'
        )
    else:
        # Do not disclose internal paths, helper responses, or configuration.
        message = 'YAML deployment failed. Inspect RSFX service logs for details.'
    if saved:
        message = 'Style saved locally, but ' + message
    return HTTPException(status_code=500, detail=message)


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
        path=sync_yaml(style)
    except Exception as exc:
        raise _yaml_sync_error(exc, saved=True) from exc
    try:
        db.set_style_yaml_path(style.id,str(path) if path else None)
        if path:db.mark_yaml_changed()
    except Exception as exc: raise _yaml_sync_error(exc, saved=True) from exc
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
        path=sync_yaml(s)
    except Exception as exc:
        raise _yaml_sync_error(exc, saved=True) from exc
    try:
        db.set_style_yaml_path(s.id,str(path) if path else None)
        if path:db.mark_yaml_changed()
    except Exception as exc: raise _yaml_sync_error(exc, saved=True) from exc
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
    try:
        p=sync_yaml(s)
    except Exception as exc:
        raise _yaml_sync_error(exc, saved=False) from exc
    try:
        db.set_style_yaml_path(style_id,str(p) if p else None)
        if p:db.mark_yaml_changed()
    except Exception as exc:
        raise _yaml_sync_error(exc, saved=False) from exc
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


def _holiday_runtime_channel_name(req, style, context: dict) -> str:
    """Return a trustworthy channel label, never the currently playing title.

    Legacy ErsatzTV does not always supply a channel display name. In
    particular, older adapter payloads may carry Channel_Title (the *program*
    title) in the channel_name slot. Keep channel/movie identities separate.
    """
    epg = context.get('Epg') or []
    current = epg[0] if isinstance(epg, list) and epg and isinstance(epg[0], dict) else {}
    program_names = {
        str(value).strip().casefold()
        for value in (
            current.get('Title'), current.get('SubTitle'),
            context.get('MediaItem_ShowTitle'), context.get('MediaItem_Title'),
        )
        if value
    }
    # Prefer the explicit, user-set channel label when supplied. The renderer
    # handles that exact override independently of runtime metadata.
    override = (style.appearance.channel_label_text or '').strip()
    if override:
        return override

    # Explicit channel-name fields are preferred to ambiguous title aliases.
    candidates = (
        context.get('Channel_Name'), context.get('ChannelName'),
        context.get('channel_name'), context.get('channelName'),
        req.channel_name,
    )
    for candidate in candidates:
        if candidate is None or isinstance(candidate, (dict, list)):
            continue
        value = str(candidate).strip()
        if value and value.casefold() not in program_names:
            return value[:160]

    # If ErsatzTV exposes only a channel ID, a custom Style name is a
    # more useful on-screen fallback than a changing program title.
    return (style.display_name or 'Holiday Channel').strip()[:160]


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

    if style.appearance.theme == 'holiday-broadcast':
        runtime_name = _holiday_runtime_channel_name(req, style, context)
    else:
        # Preserve non-holiday template behavior for v0.1.1.
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
