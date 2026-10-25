const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const types = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime'};
http.createServer((req,res)=>{
  let file;
  try {file = path.resolve(__dirname, '.' + decodeURIComponent(new URL(req.url,'http://localhost').pathname));} catch {res.writeHead(400).end();return;}
  if(file===__dirname) file=path.join(__dirname,'index.html');
  if(!file.startsWith(__dirname+path.sep)) {res.writeHead(403).end();return;}
  fs.stat(file,(err,stat)=>{
    if(err || !stat.isFile()){res.writeHead(404).end('Not found');return;}
    res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','Content-Length':stat.size});
    fs.createReadStream(file).pipe(res);
  });
}).listen(3000,'127.0.0.1',()=>console.log('Local: http://127.0.0.1:3000'));
