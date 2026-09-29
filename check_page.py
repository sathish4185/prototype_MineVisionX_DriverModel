import json
import urllib.request
try:
    import websocket
except ImportError:
    import sys
    print("websocket-client not installed")
    sys.exit(0)

resp = urllib.request.urlopen('http://127.0.0.1:9222/json')
pages = json.loads(resp.read().decode())
page = [p for p in pages if p.get('type') == 'page'][0]
ws_url = page['webSocketDebuggerUrl']

ws = websocket.create_connection(ws_url)
req = {
    'id': 1,
    'method': 'Runtime.evaluate',
    'params': {
        'expression': 'JSON.stringify({leafletLoaded: typeof L !== "undefined", hasMap: !!leafletMap, tileImgs: Array.from(document.querySelectorAll("#live-google-map img")).map(i => ({src: i.src, complete: i.complete, naturalWidth: i.naturalWidth})).slice(0, 5)})'
    }
}
ws.send(json.dumps(req))
res = json.loads(ws.recv())
print("Result:", res.get('result', {}).get('result', {}).get('value'))
ws.close()
