import {renderDiagnostics,reportCsv} from './battle_report.js';
const $=s=>document.querySelector(s);
let current=null,busy=false,selected='';
async function read(path){const r=await fetch(path,{cache:'no-store'});const data=await r.json();if(!r.ok||data.ok===false)throw new Error(data.error||'读取失败');return data;}
async function refresh(){
  if(busy)return;busy=true;
  try{
    const data=await read('/api/diagnostics');
    $('#archiveStatus').textContent=(data.archiveError?'保存异常：'+data.archiveError:'自动保存正常')+' · '+(data.directory||'')+' · 待写入 '+(data.pending||0)+' 场。界面列出最近 200 场，旧文件仍保留。';
    $('#archiveStatus').className=data.archiveError?'error':'';
    const rows=new Map([...(data.archives||[]),...(data.live||[])].map(r=>[r.matchId,r]));
    const liveIds=new Set((data.live||[]).map(r=>r.matchId));
    const menu=$('#matches');menu.replaceChildren();
    for(const row of [...rows.values()].sort((a,b)=>b.startedAt-a.startedAt)){
      const option=document.createElement('option');option.value=row.matchId;
      option.textContent=new Date(row.startedAt*1000).toLocaleString()+' · '+row.mapName+' · '+row.matchId+' · '+(!liveIds.has(row.matchId)&&row.status==='playing'?'中途快照 / 非终局':({playing:'进行中',finished:'已结束',abandoned:'中断 / 无人',interrupted:'服务停止'}[row.status]||row.status));
      menu.append(option);
    }
    if(rows.has(selected))menu.value=selected;
    selected=menu.value;
    if(!selected){current=null;$('#status').textContent='暂无对局；新对局开始后会自动采集并保存。';$('#diagnostics').replaceChildren();return;}
    const requested=selected;
    const detail=await read('/api/diagnostics?matchId='+encodeURIComponent(requested));
    if(selected!==requested)return;
    current=detail.document;
    if(!detail.live&&current.status==='playing')current.status='interrupted';
    $('#diagnostics').innerHTML=renderDiagnostics(current);
    $('#status').textContent='更新于 '+new Date().toLocaleTimeString()+' · 对局 '+current.matchId+(current.report?.incomplete?' · 尚未形成完整终局战报':'');
    $('#status').className='';
  }catch(error){$('#status').textContent=error.message;$('#status').className='error';current=null;}
  finally{busy=false;$('#json').disabled=!current;$('#csv').disabled=!current?.report;}
}
function download(content,extension,type){if(!current)return;const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download='赤潮主机战报-'+current.matchId+'.'+extension;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#matches').onchange=()=>{selected=$('#matches').value;current=null;refresh();};
$('#refresh').onclick=refresh;
$('#json').onclick=()=>download(JSON.stringify(current,null,2),'json','application/json');
$('#csv').onclick=()=>{if(!current?.report)return;const {report,...serverDiagnostics}=current;download(reportCsv({...report,serverDiagnostics}),'csv','text/csv;charset=utf-8');};
setInterval(()=>{if(!document.hidden)refresh();},5000);refresh();
