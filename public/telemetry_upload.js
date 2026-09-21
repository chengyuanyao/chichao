// One bounded upload in flight. No game-loop networking, no positions or chat.
export function createTelemetryUploader({context,snapshot,probe,fetcher=fetch}) {
  let pending=null,queuedFinal=null,lastKey='',lastAt=-Infinity;
  function send(final=false) {
    const ctx=context();
    if(!ctx)return Promise.resolve(false);
    const key=ctx.roomId+':'+ctx.matchId+':'+ctx.playerId;
    if(pending) {
      if(!final)return pending;
      if(!queuedFinal)queuedFinal=pending.then(()=>{
        queuedFinal=null;
        const current=context();
        return current&&current.roomId===ctx.roomId&&current.matchId===ctx.matchId&&current.playerId===ctx.playerId&&current.token===ctx.token?send(true):false;
      });
      return queuedFinal;
    }
    if(!final&&key===lastKey&&performance.now()-lastAt<29500)return Promise.resolve(false);
    const data=snapshot(ctx.matchId,ctx.playerId,final);
    if(!data)return Promise.resolve(false);
    const body=JSON.stringify({...ctx,performance:data});
    if(new TextEncoder().encode(body).length>(final?120000:6000))return Promise.resolve(false);
    lastKey=key;lastAt=performance.now();
    const started=performance.now(),controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),4000);
    pending=(async()=>{
      try {
        const response=await fetcher('/api/telemetry',{method:'POST',headers:{'Content-Type':'application/json'},body,
          signal:controller.signal,cache:'no-store'});
        const result=await response.json();
        if(!response.ok||!result.ok)throw new Error('telemetry rejected');
        const current=context();
        if(current&&current.matchId===ctx.matchId&&current.playerId===ctx.playerId&&current.token===ctx.token)
          probe(performance.now()-started,true);
        return true;
      } catch (_) {
        const current=context();
        if(current&&current.matchId===ctx.matchId&&current.playerId===ctx.playerId&&current.token===ctx.token)probe(0,false);
        return false;
      } finally {clearTimeout(timeout);pending=null;}
    })();
    return pending;
  }
  return {send};
}
