let selectedStyleId=null,selectedStyle=null,selectedUserTemplateId=null,selectedUserTemplate=null,templateSource=null,editorMode='style',dirty=false,restartPoll=null,restartStateGeneration=0,restartWatchActive=false;
const $=id=>document.getElementById(id),num=id=>Number($(id).value);
const UI_APPEARANCE_STORAGE_KEY='rsfx-ui-appearance';
const uiAppearanceMedia=window.matchMedia
    ?window.matchMedia('(prefers-color-scheme: dark)')
    :null;

function normalizeUiAppearanceMode(value){
    return (
        value==='light'
        ||value==='dark'
        ||value==='auto'
    )
        ?value
        :'auto';
}

function effectiveUiAppearance(mode){
    mode=normalizeUiAppearanceMode(mode);

    if(mode!=='auto'){
        return mode;
    }

    return uiAppearanceMedia?.matches
        ?'dark'
        :'light';
}

function applyUiAppearance(mode,{persist=false}={}){
    mode=normalizeUiAppearanceMode(mode);

    const effective=effectiveUiAppearance(mode);

    document.documentElement.dataset.uiTheme=effective;
    document.documentElement.dataset.uiThemeMode=mode;

    const control=$('uiAppearanceTheme');

    if(control&&control.value!==mode){
        control.value=mode;
    }

    if(persist){
        try{
            localStorage.setItem(
                UI_APPEARANCE_STORAGE_KEY,
                mode
            );
        }catch(_){
            // Theme persistence is optional. The current-page
            // appearance should still work if storage is blocked.
        }
    }
}

function initUiAppearance(){
    let mode='auto';

    try{
        mode=normalizeUiAppearanceMode(
            localStorage.getItem(
                UI_APPEARANCE_STORAGE_KEY
            )||'auto'
        );
    }catch(_){
        mode='auto';
    }

    applyUiAppearance(mode);

    const control=$('uiAppearanceTheme');

    if(control){
        control.value=mode;

        control.addEventListener(
            'change',
            ()=>{
                applyUiAppearance(
                    control.value,
                    {
                        persist:true
                    }
                );
            }
        );
    }

    const onSystemAppearanceChange=()=>{
        if(
            document.documentElement
                .dataset.uiThemeMode
            ==='auto'
        ){
            applyUiAppearance('auto');
        }
    };

    if(uiAppearanceMedia){
        if(uiAppearanceMedia.addEventListener){
            uiAppearanceMedia.addEventListener(
                'change',
                onSystemAppearanceChange
            );
        }else if(uiAppearanceMedia.addListener){
            uiAppearanceMedia.addListener(
                onSystemAppearanceChange
            );
        }
    }
}

async function jf(url,opts={}){const r=await fetch(url,{cache:'no-store',...opts});if(r.status===204)return null;const t=await r.text();let b;try{b=t?JSON.parse(t):null}catch{b=t}if(!r.ok)throw new Error(b?.detail||b||`HTTP ${r.status}`);return b}
function setState(t='',c=''){$('saveState').textContent=t;$('saveState').className=`save-state ${c}`.trim()}
// RSFX_CHANNEL_DROPDOWN_MANUAL_V1
function setErsatzState(title,detail,kind=''){
  const h=$('ersatzStyleState'), help=$('manualSyncDetails');
  const expanded=help.open;
  h.className=`integration-state ${kind}`.trim();
  h.replaceChildren();
  const strong=document.createElement('strong');strong.textContent=title;
  const para=document.createElement('p');para.className='subtext';para.textContent=detail;
  h.append(strong,para,help);
  help.open=expanded;
}
let rsfxChannels=[],rsfxLastSyncChannel='',rsfxManualGeneration=0;
async function refreshErsatzChannels(){
  const select=$('syncChannel');
  let prior=select.value;
  if(!prior){try{prior=sessionStorage.getItem('rsfxSyncChannel')||'';}catch(_error){}}
  $('syncChannelStatus').textContent='Loading ErsatzTV channels…';
  try{
    const data=await jf('/v1/integration/ersatztv/channels');
    rsfxChannels=Array.isArray(data.channels)?data.channels:[];
    select.replaceChildren();
    const auto=document.createElement('option');auto.value='';auto.textContent='Auto-detect available channel';
    select.append(auto);
    for(const c of rsfxChannels){
      const option=document.createElement('option');option.value=c.number;
      option.textContent=`${c.number} — ${c.name}`;
      select.append(option);
    }
    select.value=rsfxChannels.some(c=>c.number===prior)?prior:'';
    if(prior&&!select.value){try{sessionStorage.removeItem('rsfxSyncChannel');}catch(_error){}}
    $('syncChannelStatus').textContent=`${rsfxChannels.length} channel(s) available`;
    await updateManualCommand();
  }catch(e){
    rsfxChannels=[];
    $('syncChannelStatus').textContent='Channel discovery failed: '+e.message;
    $('manualSyncCommand').textContent='Channel list unavailable. Refresh the channel list and try again.';
    $('manualSyncNotice').textContent='';
    $('copyManualSync').disabled=true;
  }
}
async function updateManualCommand(){
  const generation=++rsfxManualGeneration;
  if(!rsfxChannels.length){$('copyManualSync').disabled=true;return;}
  const channel=$('syncChannel').value||rsfxLastSyncChannel||'';
  $('manualSyncCommand').textContent='Generating command…';
  $('copyManualSync').disabled=true;
  try{
    const data=await jf('/v1/integration/ersatztv/manual-sync?channel='+encodeURIComponent(channel));
    if(generation!==rsfxManualGeneration)return;
    $('manualSyncCommand').textContent=data.command||'Command withheld: IPTV authentication is configured.';
    $('manualSyncNotice').textContent=data.notice||'';
    $('copyManualSync').disabled=!data.command;
  }catch(e){
    if(generation!==rsfxManualGeneration)return;
    $('manualSyncCommand').textContent='Unable to generate command: '+e.message;
    $('manualSyncNotice').textContent='';
    $('copyManualSync').disabled=true;
  }
}
$('syncChannel').addEventListener('change',()=>{
  try{sessionStorage.setItem('rsfxSyncChannel',$('syncChannel').value);}catch(_error){}
  rsfxLastSyncChannel='';
  updateManualCommand();
});
$('refreshChannelList').addEventListener('click',refreshErsatzChannels);
$('manualSyncDetails').addEventListener('toggle',()=>{
  if($('manualSyncDetails').open)updateManualCommand();
});
// RSFX_MANUAL_COPY_TIMEOUT_FIX_V2
async function rsfxCopyCommand(value){
  if(navigator.clipboard&&typeof navigator.clipboard.writeText==='function'){
    try{await navigator.clipboard.writeText(value);return true;}catch(_error){}
  }
  const field=document.createElement('textarea');
  field.value=value;
  field.setAttribute('readonly','');
  field.setAttribute('aria-label','Temporary copy buffer');
  field.style.position='fixed';field.style.top='0';field.style.left='-9999px';
  document.body.appendChild(field);
  field.focus();field.select();
  let ok=false;
  try{ok=document.execCommand('copy');}catch(_error){}
  field.remove();
  return ok;
}
$('copyManualSync').addEventListener('click',async()=>{
  const button=$('copyManualSync');
  if(button.disabled)return;
  const command=$('manualSyncCommand').textContent.trim();
  if(!command)return;
  const ok=await rsfxCopyCommand(command);
  if(ok){
    button.textContent='Copied!';
    setTimeout(()=>button.textContent='Copy command',1500);
  }else{
    const pre=$('manualSyncCommand');
    const range=document.createRange();range.selectNodeContents(pre);
    const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    $('manualSyncNotice').textContent='Clipboard blocked. Command selected; press Ctrl+C (Cmd+C on macOS).';
  }
});
function invalidateRestartState(){restartStateGeneration++}
async function refreshRestartState(force=false){return;} // Deprecated: restart polling cannot confirm a graphics refresh.

function markDirty(){dirty=true;invalidateRestartState();setState('Unsaved changes','dirty');if(editorMode==='style')setErsatzState('Unsaved changes','Save the Style, then use Save + Sync to request ErsatzTV registration.','dirty');updateGeneratedDescription()}
function animLabel(v){return {'slide-left':'Slide Left','slide-right':'Slide Right','slide-up':'Slide Up','slide-down':'Slide Down','fade':'Fade','none':'Static'}[v]||v}
function maxLegacyChannel(v){return Math.max(11,Math.trunc(Number(v||28)*.46))}
function maxLegacyNext(v){return Math.max(12,Math.trunc(Number(v||28)*.62))}
function generatedDescription(){const p=[];if($('trigger_tune').checked)p.push('Tune');if($('trigger_program_change').checked)p.push('Change');const m=$('trigger_position_mode').value;if(m!=='off')p.push(`${m==='elapsed'?'Position':'Remaining'} ${num('trigger_percent')}%`);if(!p.length)p.push('No Trigger');return `${animLabel($('entrance_animation_style').value)} · ${p.join(' + ')}`}
function updateGeneratedDescription(){$('generatedDescription').textContent=generatedDescription()}
function payload(){return {name:$('style_name').value.trim()||null,manage_ersatztv_yaml:$('manage_yaml').checked,overlay_display_seconds:num('display_duration'),eligibility:{start_seconds:num('elig_start'),duration_seconds:num('elig_duration')},trigger_policy:{show_on_tune:$('trigger_tune').checked,tune_delay_seconds:num('trigger_tune_delay'),show_on_program_change:$('trigger_program_change').checked,position_mode:$('trigger_position_mode').value,position_percent:num('trigger_percent')},appearance:{theme:$('theme').value,position:$('position').value,width_percent:num('width_percent'),opacity:num('opacity'),font_size:Math.round(num('now_font_size')),channel_font_size:Math.round(num('channel_font_size')),now_font_size:Math.round(num('now_font_size')),next_font_size:Math.round(num('next_font_size')),accent:$('accent').value.toUpperCase(),channel_label_text:$('channel_label_text').value.trim()||null,entrance_animation_style:$('entrance_animation_style').value,entrance_duration_seconds:num('entrance_duration'),exit_animation_style:$('exit_animation_style').value,exit_duration_seconds:num('exit_duration'),show_now:$('show_now').checked,show_next:$('show_next').checked,show_channel_label:$('show_channel_label').checked},z_index:Math.round(num('z_index'))}}
function syncPair(a,b,fromRange=false){if(fromRange)$(a).value=$(b).value;else $(b).value=$(a).value}
function bindPair(a,b){$(a).addEventListener('input',()=>{syncPair(a,b);markDirty();updatePreview()});$(b).addEventListener('input',()=>{syncPair(a,b,true);markDirty();updatePreview()})}
function animationOffset(style,phase){if(style==='slide-left')return 'translateX(-115%)';if(style==='slide-right')return 'translateX(115%)';if(style==='slide-up')return phase==='enter'?'translateY(115%)':'translateY(-115%)';if(style==='slide-down')return phase==='enter'?'translateY(-115%)':'translateY(115%)';return ''}
function previewAnimation(phase='enter'){const o=$('previewOverlay'),enter=phase==='enter',style=$(enter?'entrance_animation_style':'exit_animation_style').value,d=Math.max(0,num(enter?'entrance_duration':'exit_duration')),base=o.dataset.baseTransform||'',target=animationOffset(style,phase),opacity=num('opacity');o.style.transition='none';if(enter){o.style.transform=target?`${base} ${target}`.trim():base;o.style.opacity=style==='fade'?'0':opacity;requestAnimationFrame(()=>requestAnimationFrame(()=>{o.style.transition=`transform ${d}s ease, opacity ${d}s ease`;o.style.transform=base;o.style.opacity=opacity}))}else{o.style.transform=base;o.style.opacity=opacity;requestAnimationFrame(()=>requestAnimationFrame(()=>{o.style.transition=`transform ${d}s ease, opacity ${d}s ease`;o.style.transform=target?`${base} ${target}`.trim():base;o.style.opacity=style==='fade'?'0':opacity;setTimeout(()=>{o.style.transition='none';o.style.transform=base;o.style.opacity=opacity},Math.max(50,d*1000+100))}))}}
function previewPalette(accent,opacity){return {panel:`rgba(10,12,18,${opacity})`,navy:`rgba(18,26,58,${opacity})`,purple:`rgba(46,36,82,${opacity})`,glass:`rgba(12,34,58,${opacity})`,cream:`rgba(238,235,220,${opacity})`,black:`rgba(5,5,7,${opacity})`,dark:`rgba(14,18,24,${opacity})`,charcoal:`rgba(14,16,20,${opacity})`,accent,accent_soft:accent+'58',hot:'#FF5D6C',light:'#F5F7FA',muted:'#D2D6DE',ink:'#232323',ink_muted:'#4B4B4B'}}
function previewBox(el,s){el.style.left=`${(s.x||0)*100}%`;el.style.top=`${(s.y||0)*100}%`;el.style.width=`${(s.w||1)*100}%`;el.style.height=`${(s.h||1)*100}%`}
function compositionForTheme(theme){return window.rsfxCompositions?.[theme]||window.rsfxCompositions?.['classic-cable']||null}
function thumbnailTextSpec(key,region){
    const width=Number(region?.w||0);
    const height=Number(region?.h||0);

    let text='';
    let preferred=6;
    let minimum=5;
    let weight=700;

    if(key==='channel'){
        text=width<0.18?'6':'CH 6';
        preferred=Math.max(
            5,
            Math.min(
                7,
                Math.round(height*42)
            )
        );
        minimum=5;
    }else if(key==='now'){
        text=width<0.45
            ?'NOW  LIVE'
            :'NOW  PROGRAM';

        preferred=Math.max(
            6,
            Math.min(
                9,
                Math.round(height*30)
            )
        );

        minimum=6;
    }else{
        text=width<0.40
            ?'NEXT'
            :'NEXT  UP NEXT';

        preferred=Math.max(
            5,
            Math.min(
                7,
                Math.round(height*40)
            )
        );

        minimum=5;
        weight=600;
    }

    return {
        text,
        preferred,
        minimum,
        weight,
    };
}

let thumbnailMeasureCanvas=null;

function thumbnailMeasureContext(size,weight){
    if(!thumbnailMeasureCanvas){
        thumbnailMeasureCanvas=document.createElement('canvas');
    }

    const ctx=thumbnailMeasureCanvas.getContext('2d');

    ctx.font=`${weight} ${size}px "DejaVu Sans","Liberation Sans",sans-serif`;

    return ctx;
}

function thumbnailFitText(
    text,
    estimatedWidth,
    preferred,
    minimum,
    weight
){
    for(
        let size=preferred;
        size>=minimum;
        size--
    ){
        const ctx=thumbnailMeasureContext(
            size,
            weight
        );

        if(
            ctx.measureText(text).width
            <=estimatedWidth
        ){
            return {
                text,
                size,
            };
        }
    }

    const size=minimum;
    const ctx=thumbnailMeasureContext(
        size,
        weight
    );

    if(
        ctx.measureText(text).width
        <=estimatedWidth
    ){
        return {
            text,
            size,
        };
    }

    let clipped=text;

    while(clipped.length>1){
        clipped=clipped.slice(0,-1).trimEnd();

        const candidate=`${clipped}…`;

        if(
            ctx.measureText(candidate).width
            <=estimatedWidth
        ){
            return {
                text:candidate,
                size,
            };
        }
    }

    return {
        text:'…',
        size,
    };
}

function renderTemplateThumbnail(host,t){
    const comp=t.composition;
    const appearance=t.style.appearance;

    const pal=previewPalette(
        (
            appearance.accent
            ||'#F5C242'
        ).toLowerCase(),
        appearance.opacity??.92
    );

    host.innerHTML='';

    for(const spec of (comp.panels||[])){
        const panel=document.createElement('div');

        panel.className='composition-panel';

        if(spec.kind==='polygon'){
            const points=spec.points.map(
                point=>
                    `${point[0]*100}% ${point[1]*100}%`
            ).join(',');

            panel.style.inset='0';
            panel.style.clipPath=`polygon(${points})`;
        }else{
            previewBox(
                panel,
                spec
            );

            if(spec.kind==='ellipse'){
                panel.style.borderRadius='50%';
            }else if(spec.kind==='round_rect'){
                panel.style.borderRadius=
                    `${Math.max(
                        2,
                        Math.round(
                            (spec.radius||.08)
                            *40
                        )
                    )}px`;
            }
        }

        panel.style.background=
            pal[spec.fill]
            ||pal.panel;

        host.appendChild(panel);
    }

    const estimatedHostWidth=220;

    for(const key of [
        'channel',
        'now',
        'next'
    ]){
        if(
            key==='channel'
            &&appearance.show_channel_label===false
        ){
            continue;
        }

        if(
            key==='now'
            &&appearance.show_now===false
        ){
            continue;
        }

        if(
            key==='next'
            &&appearance.show_next===false
        ){
            continue;
        }

        const region=comp.regions?.[key];

        if(!region){
            continue;
        }

        const textSpec=thumbnailTextSpec(
            key,
            region
        );

        /*
         * Card widths vary slightly with the responsive grid.
         * Use a conservative reference width so text that fits
         * here will remain bounded on the smallest normal card.
         */
        const estimatedWidth=Math.max(
            12,
            estimatedHostWidth
            *Number(region.w||0)
            -6
        );

        const fitted=thumbnailFitText(
            textSpec.text,
            estimatedWidth,
            textSpec.preferred,
            textSpec.minimum,
            textSpec.weight
        );

        const el=document.createElement('div');

        el.className=
            `thumbnail-text thumbnail-${key}`;

        previewBox(
            el,
            region
        );

        el.style.color=
            pal[region.color]
            ||pal.light;

        el.style.textAlign=
            region.align
            ||'left';

        el.style.justifyContent=
            region.align==='center'
                ?'center'
                :region.align==='right'
                    ?'flex-end'
                    :'flex-start';

        el.style.fontSize=
            `${fitted.size}px`;

        el.style.fontWeight=
            String(textSpec.weight);

        el.textContent=
            fitted.text;

        host.appendChild(el);
    }
}
function previewRegion(){const stage=$('previewStage'),ratio=stage.clientWidth/Math.max(1,stage.clientHeight),logical=Math.abs(ratio-(16/9))<.08?{w:1280,h:720}:{w:640,h:480},lw=logical.w,lh=logical.h,w=Math.min(Math.max(220,Math.trunc(lw*num('width_percent')/100)),Math.max(220,lw-16)),preferredH=Math.trunc(Math.max(num('channel_font_size'),num('now_font_size'),num('next_font_size'))*4.75),h=Math.min(lh-16,Math.max(118,preferredH)),mx=Math.max(8,Math.trunc(lw*.035)),my=Math.max(8,Math.trunc(lh*.055)),p=$('position').value;let x,y;if(p.endsWith('left'))x=mx;else if(p.endsWith('right'))x=lw-w-mx;else x=Math.floor((lw-w)/2);if(p.startsWith('top'))y=my;else y=lh-h-my;return{x:Math.max(0,x),y:Math.max(0,y),w,h,lw,lh}}

let previewMeasureCanvas=null;

function previewScale(){
    const r=previewRegion();
    const stage=$('previewStage');
    return (stage.clientWidth/Math.max(1,r.lw));
}
function previewMeasureContext(size,bold){
    if(!previewMeasureCanvas) previewMeasureCanvas=document.createElement('canvas');
    const ctx=previewMeasureCanvas.getContext('2d');
    ctx.font=`${bold?700:400} ${size}px "DejaVu Sans","Liberation Sans",sans-serif`;
    return ctx;
}
function previewTextWidth(ctx,text){return ctx.measureText(text||'').width}
function previewLineHeight(ctx,size){const m=ctx.measureText('Ag');return Math.max(1,(m.actualBoundingBoxAscent||size*.78)+(m.actualBoundingBoxDescent||size*.22))}
function previewTruncate(ctx,text,maxw){text=text||'';if(previewTextWidth(ctx,text)<=maxw)return text;const ellipsis='…';while(text){text=text.slice(0,-1);const candidate=text.trimEnd()+ellipsis;if(previewTextWidth(ctx,candidate)<=maxw)return candidate}return ellipsis}
function previewWrapWords(ctx,text,maxw){const words=(text||'').split(/\s+/).filter(Boolean);if(!words.length)return [''];const lines=[];let current='';for(const word of words){const candidate=current?`${current} ${word}`:word;if(previewTextWidth(ctx,candidate)<=maxw){current=candidate;continue}if(current){lines.push(current);current=''}if(previewTextWidth(ctx,word)<=maxw){current=word;continue}let piece='';for(const char of word){const candidate=piece+char;if(piece&&previewTextWidth(ctx,candidate)>maxw){lines.push(piece);piece=char}else piece=candidate}current=piece}if(current)lines.push(current);return lines}
function previewVisibleLines(ctx,lines,maxw,maxLines){if(lines.length<=maxLines)return lines;const visible=lines.slice(0,maxLines),remaining=lines.slice(maxLines-1).join(' ');visible[visible.length-1]=previewTruncate(ctx,remaining,maxw);return visible}
function previewTextHeight(ctx,size,lineCount,scale){if(lineCount<=0)return 0;const lineH=previewLineHeight(ctx,size),gap=Math.max(2*scale,lineH*.12);return lineCount*lineH+Math.max(0,lineCount-1)*gap}
function previewFitWrappedText(text,maxw,maxh,maxLines,preferred,minimum,bold){const scale=previewScale(),pref=Math.max(1,Math.trunc(preferred)),min=Math.max(1,Math.min(Math.trunc(minimum),pref));for(let logical=pref;logical>=min;logical--){const size=logical*scale,ctx=previewMeasureContext(size,bold),lines=previewWrapWords(ctx,text,maxw);if(lines.length<=maxLines&&previewTextHeight(ctx,size,lines.length,scale)<=maxh)return{size,lines}}let size=min*scale,ctx=previewMeasureContext(size,bold),lines=previewVisibleLines(ctx,previewWrapWords(ctx,text,maxw),maxw,maxLines);if(previewTextHeight(ctx,size,lines.length,scale)<=maxh)return{size,lines};for(let logical=min-1;logical>=8;logical--){size=logical*scale;ctx=previewMeasureContext(size,bold);lines=previewVisibleLines(ctx,previewWrapWords(ctx,text,maxw),maxw,maxLines);if(previewTextHeight(ctx,size,lines.length,scale)<=maxh)return{size,lines}}size=8*scale;ctx=previewMeasureContext(size,bold);lines=previewVisibleLines(ctx,previewWrapWords(ctx,text,maxw),maxw,maxLines);return{size,lines}}
function previewRenderLines(el,result,align,bold){const scale=previewScale(),ctx=previewMeasureContext(result.size,bold),lineH=previewLineHeight(ctx,result.size),gap=Math.max(2*scale,lineH*.12);el.innerHTML='';el.style.fontFamily='"DejaVu Sans","Liberation Sans",sans-serif';el.style.fontSize=`${result.size}px`;el.style.fontWeight=bold?'700':'400';el.style.textTransform='none';el.style.letterSpacing='0';el.style.display='flex';el.style.flexDirection='column';el.style.justifyContent='center';el.style.alignItems=align==='center'?'center':align==='right'?'flex-end':'flex-start';el.style.whiteSpace='normal';el.style.textOverflow='clip';el.style.lineHeight=`${lineH}px`;el.style.gap=`${gap}px`;for(const line of result.lines){const span=document.createElement('span');span.textContent=line;span.style.display='block';span.style.flex='0 0 auto';span.style.maxWidth='100%';span.style.textAlign=align;span.style.lineHeight=`${lineH}px`;el.appendChild(span)}}
function previewRenderSingleLine(el,text,logicalSize,align,bold){const scale=previewScale(),size=logicalSize*scale,ctx=previewMeasureContext(size,bold),label=previewTruncate(ctx,text,el.clientWidth);previewRenderLines(el,{size,lines:[label]},align,bold)}

function updatePreview(){
    updateGeneratedDescription();
    const o=$('previewOverlay');
    const ac=$('accent');
    const theme=$('theme').value;
    const opacity=num('opacity');
    const comp=compositionForTheme(theme);
    const r=previewRegion();
    o.className='preview-overlay composition-preview';
    o.style.width=`${r.w/r.lw*100}%`;
    o.style.height=`${r.h/r.lh*100}%`;
    o.style.minHeight='0';
    o.style.opacity=opacity;
    o.style.left=`${r.x/r.lw*100}%`;
    o.style.top=`${r.y/r.lh*100}%`;
    o.style.right='';
    o.style.bottom='';
    o.style.transform='';
    o.dataset.baseTransform='';
    $('accentText').textContent=ac.value.toUpperCase();
    if(comp){
        const pal=previewPalette(ac.value,opacity);
        o.innerHTML='';
        for(const s of (comp.panels||[])){
            const e=document.createElement('div');
            e.className='composition-panel';
            if(s.kind==='polygon'){
                const xs=s.points.map(q=>q[0]*100+'% '+q[1]*100+'%').join(',');
                e.style.inset='0';
                e.style.clipPath=`polygon(${xs})`;
            }else{
                previewBox(e,s);
                if(s.kind==='ellipse')e.style.borderRadius='50%';
                else if(s.kind==='round_rect')e.style.borderRadius=`${Math.round((s.radius||.08)*100)}px`;
            }
            e.style.background=pal[s.fill]||pal.panel;
            o.appendChild(e);
        }
        const samples={channel:$('channel_label_text').value.trim()||'Saturday Morning Cartoons',now:"NOW  Scooby's All Star Laff-A-Lympics — The Diabolical Disc Demon",next:'NEXT  Snorks — Dr. Strangesnork'};
        const channelPreferred=Math.trunc(num('channel_font_size'));
        const nowPreferred=Math.trunc(num('now_font_size'));
        const nextPreferred=Math.trunc(num('next_font_size'));
        for(const key of ['channel','now','next']){
            if(key==='channel'&&!$('show_channel_label').checked)continue;
            if(key==='now'&&!$('show_now').checked)continue;
            if(key==='next'&&!$('show_next').checked)continue;
            const s=comp.regions?.[key];
            if(!s)continue;
            const e=document.createElement('div');
            e.className=`composition-text composition-${key}`;
            previewBox(e,s);
            e.style.color=pal[s.color]||pal.light;
            o.appendChild(e);
            const align=s.align||'left';
            if(key==='channel'){
                const result=previewFitWrappedText(samples[key],e.clientWidth,e.clientHeight,1,channelPreferred,Math.max(8,Math.trunc(channelPreferred*.70)),true);
                previewRenderLines(e,result,align,true);
            }else if(key==='now'){
                const result=previewFitWrappedText(samples[key],e.clientWidth,e.clientHeight,2,nowPreferred,Math.max(8,Math.trunc(nowPreferred*.60)),true);
                previewRenderLines(e,result,align,true);
            }else{
                const result=previewFitWrappedText(samples[key],e.clientWidth,e.clientHeight,1,nextPreferred,Math.max(8,Math.trunc(nextPreferred*.65)),false);
                previewRenderLines(e,result,align,false);
            }
        }
    }
    previewAnimation();
}

function isTemplateMode(){return editorMode==='template-new'||editorMode==='template-edit'}

function setEditorMode(mode){
    editorMode=mode;

    const templateMode=isTemplateMode();

    $('templateMeta').style.display=templateMode?'':'none';
    $('manageYamlLabel').style.display=templateMode?'none':'';
    $('ersatzFieldset').style.display=templateMode?'none':'';
    $('createStyleFromTemplate').style.display=templateMode?'':'none';
    $('syncYaml').style.display=templateMode?'none':'';
    $('saveAndSync').style.display=templateMode?'none':'';

    $('manage_yaml').disabled=templateMode;

    if(templateMode){
        $('manage_yaml').checked=true;
        $('styleNameLabel').textContent='Template name';
        $('styleNameHelp').textContent='This names the reusable user template. The name is separate from its persistent ID and slug.';
        $('saveStyleButton').textContent=mode==='template-edit'?'Save template':'Save as new template';
        $('deleteStyle').textContent='Delete template';
        $('deleteStyle').disabled=mode!=='template-edit';
        $('reloadStyle').disabled=mode!=='template-edit';
    }else{
        $('deleteStyle').textContent='Delete style';
        $('syncYaml').style.display='';
        $('manage_yaml').disabled=false;
    }
}

function templateStylePayload(){
    const p=payload();

    // Template persistence is not runtime persistence.
    // Do not bake a template display name into Style.name and do
    // not disable future YAML management merely because the object
    // is currently being stored as a template.
    p.name=null;
    p.manage_ersatztv_yaml=true;

    return p;
}

function templatePayload(){
    return {
        name:$('style_name').value.trim(),
        description:$('template_description').value.trim()||null,
        source_kind:templateSource?.kind||null,
        source_template_id:templateSource?.id==null?null:String(templateSource.id),
        source_template_name:templateSource?.name||null,
        style:templateStylePayload(),
    };
}

function templateProvenanceText(){
    if(!templateSource){
        return 'Independent user template. Saving this does not create ErsatzTV YAML.';
    }

    const kind=templateSource.kind==='builtin'?'built-in template':'user template';

    return `Cloned from ${kind}: ${templateSource.name}. Provenance is informational only; this copy is independent after save.`;
}

function updateTemplateModeUi(){
    $('templateProvenance').textContent=templateProvenanceText();

    if(editorMode==='template-new'){
        $('templateModeLabel').textContent='New user template';
    }else if(editorMode==='template-edit'){
        $('templateModeLabel').textContent=`User template ID ${selectedUserTemplateId}`;
    }
}

function updateStyleNameUi(existing){
    const label=$('styleNameLabel');
    const help=$('styleNameHelp');
    const button=$('saveStyleButton');

    if(existing){
        label.textContent='Style name / rename';
        help.textContent='Change this name and save to rename the existing Style. Style ID, assignments, slug, settings, and managed YAML path are preserved. When YAML management is enabled, the ErsatzTV Script Graphics display name is updated and can be refreshed using Save + Sync to ErsatzTV.';
        button.textContent='Save';
    }else{
        label.textContent='Style name';
        help.textContent='Give this Style a meaningful name, or leave it blank to use the generated behavioral description.';
        button.textContent='Save';
    }
}

function loadStyle(s,{checkRestart=true}={}){
    setEditorMode('style');
    templateSource=null;
    selectedUserTemplateId=null;
    selectedUserTemplate=null;

    invalidateRestartState();

    selectedStyle=s||null;
    selectedStyleId=s?.id||null;

    $('style_name').value=s?.name||'';
    $('template_description').value='';
    $('manage_yaml').checked=s?.manage_ersatztv_yaml??true;
    $('z_index').value=s?.z_index??20;
    $('display_duration').value=s?.overlay_display_seconds??7;
    $('elig_start').value=s?.eligibility?.start_seconds??0;
    $('elig_duration').value=s?.eligibility?.duration_seconds??21600;
    $('trigger_tune').checked=s?.trigger_policy?.show_on_tune??true;
    $('trigger_tune_delay').value=s?.trigger_policy?.tune_delay_seconds??2;
    $('trigger_program_change').checked=s?.trigger_policy?.show_on_program_change??false;
    $('trigger_position_mode').value=s?.trigger_policy?.position_mode??'off';
    $('trigger_percent').value=s?.trigger_policy?.position_percent??50;
    $('theme').value=s?.appearance?.theme??'classic-cable';
    $('position').value=s?.appearance?.position??'bottom-left';
    $('width_percent').value=s?.appearance?.width_percent??62;
    $('opacity').value=s?.appearance?.opacity??.92;
    $('channel_font_size').value=s?.appearance?.channel_font_size??maxLegacyChannel(s?.appearance?.font_size??28);
    $('now_font_size').value=s?.appearance?.now_font_size??s?.appearance?.font_size??28;
    $('next_font_size').value=s?.appearance?.next_font_size??maxLegacyNext(s?.appearance?.font_size??28);
    $('accent').value=(s?.appearance?.accent??'#F5C242').toLowerCase();
    $('channel_label_text').value=s?.appearance?.channel_label_text??'';
    $('entrance_animation_style').value=s?.appearance?.entrance_animation_style??'slide-left';
    $('entrance_duration').value=s?.appearance?.entrance_duration_seconds??.45;
    $('exit_animation_style').value=s?.appearance?.exit_animation_style??'none';
    $('exit_duration').value=s?.appearance?.exit_duration_seconds??.35;
    $('show_now').checked=s?.appearance?.show_now??true;
    $('show_next').checked=s?.appearance?.show_next??true;
    $('show_channel_label').checked=s?.appearance?.show_channel_label??true;

    [
        ['display_duration','display_duration_range'],
        ['trigger_percent','trigger_percent_range'],
        ['width_percent','width_percent_range'],
        ['opacity','opacity_range'],
        ['channel_font_size','channel_font_size_range'],
        ['now_font_size','now_font_size_range'],
        ['next_font_size','next_font_size_range']
    ].forEach(x=>syncPair(...x));

    $('editorTitle').textContent=s?`Edit ${s.display_name||s.name||s.slug}`:'Add Style';
    $('editorSubtitle').textContent=s
        ?(s.name?`Configuration: ${s.generated_description}`:'Automatically named from animation and triggers.')
        :'Name is optional; blank Styles are automatically named and deduplicated.';

    $('deleteStyle').disabled=!s;
    $('syncYaml').disabled=!s;
    $('reloadStyle').disabled=!s;

    updateStyleNameUi(Boolean(s));

    dirty=false;
    setState();

    if(!s){
        setErsatzState(
            'Not saved yet',
            'Saving a managed Style writes its Script Graphics YAML into the configured ErsatzTV directory.'
        );
    }else if(s.manage_ersatztv_yaml){
        setErsatzState(
            'YAML saved',
            'Use Save + Sync to request ErsatzTV graphics registration.'
        );

        // No restart polling. Manual sync has its own state.
    }else{
        setErsatzState(
            'Saved · YAML management disabled',
            'RSFX is not writing this Style into the ErsatzTV Script Graphics directory.'
        );
    }

    updatePreview();
}
async function refresh(){const styles=await jf('/v1/styles');window.rsfxStyles=styles;const sh=$('styles');sh.innerHTML='';if(!styles.length)sh.innerHTML='<p class="subtext">No Styles yet.</p>';styles.forEach(s=>{const r=document.createElement('div');r.className='row';r.innerHTML=`<div><strong>${s.display_name||s.name||s.slug}</strong><small>${s.generated_description}</small></div><div><span class="badge">${s.slug}</span><span class="badge">ID ${s.id}</span></div>`;r.onclick=()=>loadStyle(s);sh.appendChild(r)})}
function loadTemplateValues(s){
    $('z_index').value=s.z_index??20;
    $('display_duration').value=s.overlay_display_seconds??7;
    $('elig_start').value=s.eligibility?.start_seconds??0;
    $('elig_duration').value=s.eligibility?.duration_seconds??21600;
    $('trigger_tune').checked=s.trigger_policy?.show_on_tune??true;
    $('trigger_tune_delay').value=s.trigger_policy?.tune_delay_seconds??2;
    $('trigger_program_change').checked=s.trigger_policy?.show_on_program_change??false;
    $('trigger_position_mode').value=s.trigger_policy?.position_mode??'off';
    $('trigger_percent').value=s.trigger_policy?.position_percent??50;
    $('theme').value=s.appearance?.theme??'classic-cable';
    $('position').value=s.appearance?.position??'bottom-left';
    $('width_percent').value=s.appearance?.width_percent??62;
    $('opacity').value=s.appearance?.opacity??.92;
    $('channel_font_size').value=s.appearance?.channel_font_size??maxLegacyChannel(s.appearance?.font_size??28);
    $('now_font_size').value=s.appearance?.now_font_size??s.appearance?.font_size??28;
    $('next_font_size').value=s.appearance?.next_font_size??maxLegacyNext(s.appearance?.font_size??28);
    $('accent').value=(s.appearance?.accent??'#F5C242').toLowerCase();
    $('channel_label_text').value=s.appearance?.channel_label_text??'';
    $('entrance_animation_style').value=s.appearance?.entrance_animation_style??'slide-left';
    $('entrance_duration').value=s.appearance?.entrance_duration_seconds??.45;
    $('exit_animation_style').value=s.appearance?.exit_animation_style??'none';
    $('exit_duration').value=s.appearance?.exit_duration_seconds??.35;
    $('show_now').checked=s.appearance?.show_now??true;
    $('show_next').checked=s.appearance?.show_next??true;
    $('show_channel_label').checked=s.appearance?.show_channel_label??true;

    [
        ['display_duration','display_duration_range'],
        ['trigger_percent','trigger_percent_range'],
        ['width_percent','width_percent_range'],
        ['opacity','opacity_range'],
        ['channel_font_size','channel_font_size_range'],
        ['now_font_size','now_font_size_range'],
        ['next_font_size','next_font_size_range']
    ].forEach(x=>syncPair(...x));
}

function useTemplateAsStyle(t){
    const s=structuredClone(t.style);

    loadStyle(null);
    loadTemplateValues(s);

    $('style_name').value=t.name;
    $('manage_yaml').checked=true;

    $('editorTitle').textContent=`New Style from ${t.name}`;
    $('editorSubtitle').textContent=t.builtin
        ?'Built-in template loaded as a new reusable Style.'
        :'Saved user template loaded as a new reusable Style.';

    dirty=true;
    setState('Template loaded · Style not saved','dirty');

    setErsatzState(
        'Template preview',
        'No ErsatzTV YAML has been created. Save this Style when you are ready.'
    );

    updatePreview();

    document.querySelector('.editor-card')?.scrollIntoView({
        behavior:'smooth',
        block:'start'
    });
}

function cloneBuiltInTemplate(t){
    loadStyle(null);
    loadTemplateValues(structuredClone(t.style));

    selectedStyle=null;
    selectedStyleId=null;
    selectedUserTemplate=null;
    selectedUserTemplateId=null;

    templateSource={
        kind:'builtin',
        id:t.id,
        name:t.name
    };

    setEditorMode('template-new');

    $('style_name').value=`${t.name} Copy`;
    $('template_description').value=t.description||'';

    $('editorTitle').textContent=`Customize ${t.name}`;
    $('editorSubtitle').textContent='Editing an independent copy. The built-in source cannot be modified.';

    updateTemplateModeUi();

    dirty=true;
    setState('Template copy · not saved','dirty');

    updatePreview();

    document.querySelector('.editor-card')?.scrollIntoView({
        behavior:'smooth',
        block:'start'
    });
}

function editUserTemplate(t){
    loadStyle(null);
    loadTemplateValues(structuredClone(t.style));

    selectedStyle=null;
    selectedStyleId=null;

    selectedUserTemplate=t;
    selectedUserTemplateId=t.id;

    templateSource=(
        t.source_kind
        ?{
            kind:t.source_kind,
            id:t.source_template_id,
            name:t.source_template_name
        }
        :null
    );

    setEditorMode('template-edit');

    $('style_name').value=t.name;
    $('template_description').value=t.description||'';

    $('editorTitle').textContent=`Edit template: ${t.name}`;
    $('editorSubtitle').textContent=`User template ID ${t.id} · slug ${t.slug}`;

    updateTemplateModeUi();

    dirty=false;
    setState('Saved user template','saved');

    updatePreview();

    document.querySelector('.editor-card')?.scrollIntoView({
        behavior:'smooth',
        block:'start'
    });
}

function cloneUserTemplate(t){
    loadStyle(null);
    loadTemplateValues(structuredClone(t.style));

    selectedStyle=null;
    selectedStyleId=null;
    selectedUserTemplate=null;
    selectedUserTemplateId=null;

    templateSource={
        kind:'user',
        id:String(t.id),
        name:t.name
    };

    setEditorMode('template-new');

    $('style_name').value=`${t.name} Copy`;
    $('template_description').value=t.description||'';

    $('editorTitle').textContent=`Clone template: ${t.name}`;
    $('editorSubtitle').textContent='Editing an independent copy of the saved user template.';

    updateTemplateModeUi();

    dirty=true;
    setState('Template clone · not saved','dirty');

    updatePreview();

    document.querySelector('.editor-card')?.scrollIntoView({
        behavior:'smooth',
        block:'start'
    });
}

function createStyleFromCurrentTemplate(){
    const templateName=$('style_name').value.trim();
    const s=templateStylePayload();

    loadStyle(null);
    loadTemplateValues(s);

    $('style_name').value=templateName;
    $('manage_yaml').checked=true;

    $('editorTitle').textContent=`New Style from ${templateName||'user template'}`;
    $('editorSubtitle').textContent='Template values copied into a new reusable FX Style. Saving this Style follows the normal ErsatzTV YAML lifecycle.';

    dirty=true;
    setState('Style copy · not saved','dirty');

    setErsatzState(
        'Not saved yet',
        'Saving this Style can write its managed Script Graphics YAML into the configured ErsatzTV directory.'
    );

    updatePreview();
}

function renderTemplateCard(host,t,kind){
    const card=document.createElement('article');
    card.className='template-card';

    const builtin=kind==='builtin';
    const family=builtin
        ?`${t.family} · Built-in`
        :'User template';

    const description=t.description||'Saved reusable user template.';

    card.innerHTML=`
        <div class="template-swatch composition-thumbnail"></div>
        <div class="family">${family}</div>
        <h3>${t.name}</h3>
        <p>${description}</p>
        <div class="template-actions"></div>
    `;

    const thumbnailData={
        ...t,
        composition:builtin
            ?t.composition
            :compositionForTheme(t.style.appearance.theme)
    };

    renderTemplateThumbnail(
        card.querySelector('.composition-thumbnail'),
        thumbnailData
    );

    const actions=card.querySelector('.template-actions');

    const use=document.createElement('button');
    use.type='button';
    use.textContent='Use as Style';
    use.onclick=()=>useTemplateAsStyle(t);
    actions.appendChild(use);

    if(builtin){
        const clone=document.createElement('button');
        clone.type='button';
        clone.textContent='Clone / customize';
        clone.onclick=()=>cloneBuiltInTemplate(t);
        actions.appendChild(clone);
    }else{
        const edit=document.createElement('button');
        edit.type='button';
        edit.textContent='Edit';
        edit.onclick=()=>editUserTemplate(t);
        actions.appendChild(edit);

        const clone=document.createElement('button');
        clone.type='button';
        clone.textContent='Clone';
        clone.onclick=()=>cloneUserTemplate(t);
        actions.appendChild(clone);
    }

    host.appendChild(card);
}

async function refreshTemplates(){
    const [builtins,userTemplates]=await Promise.all([
        jf('/v1/templates'),
        jf('/v1/user-templates')
    ]);

    window.rsfxBuiltinTemplates=builtins;
    window.rsfxUserTemplates=userTemplates;

    window.rsfxCompositions=Object.fromEntries(
        builtins.map(t=>[
            t.style.appearance.theme,
            t.composition
        ])
    );

    window.rsfxTemplates=[
        ...builtins,
        ...userTemplates
    ];

    const host=$('templates');
    host.innerHTML='';

    builtins.forEach(
        t=>renderTemplateCard(
            host,
            t,
            'builtin'
        )
    );

    userTemplates.forEach(
        t=>renderTemplateCard(
            host,
            t,
            'user'
        )
    );

    if(!builtins.length&&!userTemplates.length){
        host.innerHTML='<p class="subtext">No templates available.</p>';
    }
}

async function saveUserTemplate(){
    const p=templatePayload();

    if(!p.name){
        throw new Error(
            'Template name is required.'
        );
    }

    const editing=(
        editorMode==='template-edit'
        && selectedUserTemplateId
    );

    const url=editing
        ?`/v1/user-templates/${selectedUserTemplateId}`
        :'/v1/user-templates';

    const saved=await jf(
        url,
        {
            method:editing?'PUT':'POST',
            headers:{
                'Content-Type':'application/json'
            },
            body:JSON.stringify(p)
        }
    );

    await refreshTemplates();

    const fresh=(
        window.rsfxUserTemplates||[]
    ).find(
        x=>x.id===saved.id
    )||saved;

    editUserTemplate(fresh);

    setState(
        editing
            ?'Template saved'
            :'User template created',
        'saved'
    );

    return fresh;
}
async function saveStyle(e){
    e.preventDefault();
    const doSync=e.submitter?.id==='saveAndSync';

    try{
        if(isTemplateMode()){
            await saveUserTemplate();
            return;
        }

        const p=payload();

        if(!p.name&&!selectedStyleId){
            const m=await jf(
                '/v1/styles/match',
                {
                    method:'POST',
                    headers:{
                        'Content-Type':'application/json'
                    },
                    body:JSON.stringify(p)
                }
            );

            if(
                m.match
                &&!confirm(
                    `Matching Style already exists: ${m.match.display_name||m.match.slug}. Reuse it?`
                )
            ){
                return;
            }
        }

        invalidateRestartState();

        const url=selectedStyleId
            ?`/v1/styles/${selectedStyleId}`
            :'/v1/styles';

        const s=await jf(
            url,
            {
                method:selectedStyleId?'PUT':'POST',
                headers:{
                    'Content-Type':'application/json'
                },
                body:JSON.stringify(p)
            }
        );

        selectedStyleId=s.id;
        selectedStyle=s;

        setState(
            'Saved changes',
            'saved'
        );

        await refresh();

        const saved=(
            window.rsfxStyles||[]
        ).find(
            x=>x.id===s.id
        )||s;

        loadStyle(
            saved,
            {
                checkRestart:false
            }
        );

        setState(
            'Saved changes',
            'saved'
        );

        if(saved.manage_ersatztv_yaml){
            if(doSync){
                setErsatzState('Contacting ErsatzTV…',
                    'Requesting a one-second HLS segmenter session.');
                try{
                    const result=await jf(`/v1/styles/${saved.id}/refresh-ersatztv`,{
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({channel:$('syncChannel').value.trim()})
                    });
                    rsfxLastSyncChannel=result.channel||'';
                    updateManualCommand();
                    setErsatzState('Sync requested · verify in ErsatzTV',
                        result.message,'ready');
                    setState('Saved + sync requested','saved');
                }catch(syncError){
                    setErsatzState('YAML saved · sync request failed',
                        syncError.message,'restart');
                    setState('Saved · sync failed','error');
                }
            }else{
                setErsatzState('YAML saved · sync not requested',
                    'Use Save + Sync to request graphics registration.');
            }
        }else if(doSync){
            setErsatzState('YAML management disabled',
                'Enable Manage ErsatzTV YAML to synchronize.');
        }
    }catch(err){
        setState(
            err.message,
            'error'
        );
    }
}
async function boot(){try{const h=await jf('/v1/health');$('health').textContent=`RSFX ${h.version} · online`;$('health').className='pill ok';$('capabilities').textContent=JSON.stringify(await jf('/v1/capabilities'),null,2);await Promise.all([refresh(),refreshTemplates()]);loadStyle(null);await refreshErsatzChannels();restartPoll=setInterval(()=>refreshRestartState(),2000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshRestartState(true)});window.addEventListener('focus',()=>refreshRestartState(true))}catch(e){$('health').textContent=e.message;$('health').className='pill bad'}}
$('styleForm').addEventListener(
    'submit',
    saveStyle
);

$('newStyle').onclick=()=>loadStyle(null);

$('createStyleFromTemplate').onclick=()=>{
    if(isTemplateMode()){
        createStyleFromCurrentTemplate();
    }
};

$('reloadStyle').onclick=()=>{
    if(editorMode==='template-edit'){
        const current=(
            window.rsfxUserTemplates||[]
        ).find(
            x=>x.id===selectedUserTemplateId
        );

        if(current){
            editUserTemplate(current);
        }

        return;
    }

    if(selectedStyle){
        loadStyle(selectedStyle);
    }
};

$('syncYaml').onclick=async()=>{
    if(editorMode!=='style'){
        return;
    }

    if(selectedStyleId){
        try{
            invalidateRestartState();

            await jf(
                `/v1/styles/${selectedStyleId}/sync-ersatztv`,
                {
                    method:'POST'
                }
            );

            setState('YAML rewritten','saved');
            setErsatzState('YAML rewritten · sync not requested',
                'Use Save + Sync to request an ErsatzTV graphics refresh.');
        }catch(e){
            setState(
                e.message,
                'error'
            );
        }
    }
};

$('deleteStyle').onclick=async()=>{
    if(editorMode==='template-edit'){
        if(selectedUserTemplateId && confirm(
            'Delete this user template? Styles created from it are unaffected.'
        )){
            try{
                await jf(`/v1/user-templates/${selectedUserTemplateId}`,{method:'DELETE'});
                await refreshTemplates();
                loadStyle(null);
                setState('User template deleted','saved');
            }catch(e){setState(e.message,'error');}
        }
        return;
    }
    if(editorMode!=='style'||!selectedStyleId)return;
    if(!confirm('Delete this Style and its managed ErsatzTV YAML?\\n\\nThis cannot be undone. RSFX will request an ErsatzTV graphics refresh.'))return;
    const id=selectedStyleId;
    const channel=$('syncChannel').value.trim();
    $('deleteStyle').disabled=true;
    try{
        const result=await jf(`/v1/styles/${id}`,{method:'DELETE'});
        invalidateRestartState();
        loadStyle(null);
        await refresh();
        setState('Style deleted','saved');
        if(!result.ersatztv_restart_required){
            setErsatzState('Style deleted',
                'YAML management was disabled; no ErsatzTV refresh was needed.','ready');
            return;
        }
        setErsatzState('Style deleted · contacting ErsatzTV…',
            'Requesting a one-second graphics refresh.');
        try{
            const sync=await jf('/v1/integration/ersatztv/refresh-after-delete',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({channel})
            });
            rsfxLastSyncChannel=sync.channel||'';
            updateManualCommand();
            setErsatzState('Style deleted · sync requested',sync.message,'ready');
            setState('Deleted + sync requested','saved');
        }catch(e){
            setErsatzState('Style deleted · sync failed',
                'The deletion succeeded but the refresh request failed: '+e.message,'restart');
            setState('Deleted · refresh failed','error');
        }
    }catch(e){
        setState('Delete failed: '+e.message,'error');
    }finally{
        $('deleteStyle').disabled=!selectedStyleId;
    }
};
[
    'style_name',
    'template_description',
    'manage_yaml',
    'z_index',
    'elig_start',
    'elig_duration',
    'trigger_tune',
    'trigger_tune_delay',
    'trigger_program_change',
    'trigger_position_mode',
    'trigger_percent',
    'theme',
    'position',
    'entrance_duration',
    'exit_duration',
    'accent',
    'channel_label_text',
    'show_channel_label',
    'show_now',
    'show_next'
].forEach(
    id=>$(id).addEventListener(
        'input',
        ()=>{
            markDirty();
            updatePreview();
        }
    )
);

$('entrance_animation_style').addEventListener(
    'input',
    ()=>{
        markDirty();
        updatePreview();
    }
);

$('exit_animation_style').addEventListener(
    'input',
    ()=>{
        markDirty();
        updateGeneratedDescription();
        previewAnimation('exit');
    }
);

[
    ['display_duration','display_duration_range'],
    ['trigger_percent','trigger_percent_range'],
    ['width_percent','width_percent_range'],
    ['opacity','opacity_range'],
    ['channel_font_size','channel_font_size_range'],
    ['now_font_size','now_font_size_range'],
    ['next_font_size','next_font_size_range']
].forEach(
    x=>bindPair(...x)
);

initUiAppearance();
boot();
