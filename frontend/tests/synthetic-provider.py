from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import json,time
files={'index.html':'<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width"><meta name="description" content="QA business"><title>Audit site</title><link rel="stylesheet" href="styles.css"></head><body><main><h1>QA Business</h1><p>A real generated fixture streamed through the local backend.</p><button id="hello">Say hello</button></main><script src="script.js"></script></body></html>','styles.css':'body{margin:0;padding:32px;font-family:system-ui;background:#f4f5fa;color:#182033}h1{font-size:40px}button{padding:12px}button:focus-visible{outline:3px solid blue}@media(max-width:600px){body{padding:16px}h1{font-size:28px}}','script.js':'document.querySelector("#hello").addEventListener("click",()=>{document.querySelector("p").textContent="Hello from the generated site!"})'}
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps({'models':[{'name':'test-coder-vision:cloud','size':1000000000},{'name':'test-mini:local','size':500000000}]}).encode())
 def do_POST(self):
  data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
  if self.path=='/sdapi/v1/txt2img':
   self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();return self.wfile.write(json.dumps({'images':['iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jw4sAAAAASUVORK5CYII=']}).encode())
  content=json.dumps({'files':files,'summary':'Created a complete QA website.'}) if data['messages'][0]['role']=='system' else json.dumps({'answer':'Validated JSON probe.'})
  self.send_response(200);self.send_header('Content-Type','text/event-stream' if data.get('stream') else 'application/json');self.end_headers()
  if not data.get('stream'):return self.wfile.write(json.dumps({'choices':[{'message':{'content':content}}]}).encode())
  try:
   for i in range(0,len(content),150):
    self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':content[i:i+150]}}]})+'\n\n').encode());self.wfile.flush();time.sleep(.03)
   self.wfile.write(b'data: [DONE]\n\n')
  except BrokenPipeError:pass
ThreadingHTTPServer(('0.0.0.0',8012),H).serve_forever()
