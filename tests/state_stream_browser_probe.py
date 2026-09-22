# -*- coding: utf-8 -*-
"""Manual real-browser probe. Local synthetic room only; POST /probe-stop to exit."""
import json
import threading
import time
from urllib.parse import urlencode
from command_priority_test import make_room
import server

room, owner, _ = make_room()
server.ROOMS[room['id']] = room
query = urlencode({'roomId': room['id'], 'playerId': owner['id'], 'token': owner['token']})
info = {'connections': 0, 'gzipResponses': 0}


class ProbeHandler(server.GameHandler):
    def log_message(self, *_):
        pass

    def send_header(self, name, value):
        if name.lower() == 'content-encoding' and value == 'gzip':
            info['gzipResponses'] += 1
        super(ProbeHandler, self).send_header(name, value)

    def do_GET(self):
        if self.path == '/probe':
            page = '''<!doctype html><meta charset="utf-8"><title>SSE recovery probe</title>
<h1>Native EventSource / gzip recovery</h1><pre id="result">Running controlled silent-stall test...</pre>
<script type="module">
import {createStateStream} from '/state_stream.js';
const el=document.querySelector('#result');
let frames=0,retries=0,first=null,last=null,maxGap=0,ended=false;
const start=performance.now();
const stream=createStateStream({url:URL_VALUE,isActive:()=>true,
 onStatus(){},onReconnect(){retries++;},onState(event){
 const state=JSON.parse(event.data),now=performance.now();
 frames++;if(first===null)first=now-start;if(last!==null)maxGap=Math.max(maxGap,now-last);last=now;
 if(frames>=14 && retries && !ended){ended=true;stream.close();
 fetch('/probe-info').then(r=>r.json()).then(info=>{el.textContent=JSON.stringify({
 result:info.gzipResponses>=2?'PASS':'FAIL',frames,retries,firstFrameMs:Math.round(first),
 maxGapMs:Math.round(maxGap),elapsed:state.game.elapsed,...info},null,2);});}
}});
setTimeout(()=>{if(!ended){stream.close();el.textContent='FAIL: no bounded recovery';}},15000);
</script>'''.replace('URL_VALUE', json.dumps('/api/events?' + query))
            encoded = page.encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
        elif self.path == '/probe-info':
            self.send_json(200, info)
        else:
            super(ProbeHandler, self).do_GET()

    def do_POST(self):
        if self.path == '/probe-stop':
            self.send_json(200, {'ok': True})
            threading.Thread(target=self.server.shutdown,daemon=True).start()
        else:
            super(ProbeHandler, self).do_POST()

    def handle_events(self, query):
        info['connections'] += 1
        original = self.wfile
        if info['connections'] == 1:
            class PausedWriter(object):
                writes = 0

                def write(inner, data):
                    inner.writes += 1
                    if inner.writes == 5:
                        time.sleep(3.5)  # No close/error: recreate a half-open stream.
                    return original.write(data)

                def flush(inner):
                    return original.flush()
            self.wfile = PausedWriter()
        try:
            super(ProbeHandler, self).handle_events(query)
        finally:
            self.wfile = original


if __name__ == '__main__':
    httpd = server.ThreadedHTTPServer(('127.0.0.1',0),ProbeHandler)
    print('http://127.0.0.1:%d/probe' % httpd.server_address[1],flush=True)
    def simulation():
        while server.RUNNING:
            with server.room_lock(room):
                server.tick_game(room,.05)
            time.sleep(.05)
    threading.Thread(target=simulation,daemon=True).start()
    try:
        httpd.serve_forever()
    finally:
        server.RUNNING=False
        httpd.server_close()
