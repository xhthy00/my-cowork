/** Read-only, isolated documentation preview. No product backend or model calls. */
import { createServer as createViteServer } from 'vite';
import react from '@vitejs/plugin-react';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { dirname, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const port = Number(process.env.README_PREVIEW_PORT || 5298);
const python = resolve(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const catalog = JSON.parse(execFileSync(python, ['-c', `
import json
from pathlib import Path
from app.assistants import BUILTIN
from app.skills import load_skill_md, load_skill_yaml
assistants=[{k:v for k,v in a.items() if k != 'rules'} for a in BUILTIN]
skills=[]
for base in [Path('../skills'), Path('../resources/example-skills')]:
 for folder in sorted(base.iterdir()):
  if not folder.is_dir(): continue
  yaml=folder/'skill.yaml'; md=folder/'SKILL.md'
  if not yaml.is_file() and not md.is_file(): continue
  s=load_skill_yaml(yaml) if yaml.is_file() else load_skill_md(md)
  skills.append({'id':s.id,'name':s.name,'description':s.description,'enabled':True,'scope':{'isGlobal':True,'selectedAgents':[]},'isExample':base.name=='example-skills'})
print(json.dumps({'assistants':assistants,'skills':skills},ensure_ascii=False))
`], { cwd: resolve(root, 'backend'), encoding: 'utf8' }));

const vite = await createViteServer({
  configFile: false, root: resolve(root, 'docs/screenshots'), plugins: [react(), {
    name: 'readme-fixtures',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        if (request.url !== '/fixture/catalog.json') return next();
        response.setHeader('Content-Type', 'application/json; charset=utf-8');
        response.end(JSON.stringify(catalog));
      });
    },
  }],
  resolve: { alias: { '@': resolve(root, 'renderer/src') } },
  server: { host: '127.0.0.1', port, strictPort: true, fs: { allow: [root] } },
});
await vite.listen();

const staticRoot = resolve(root, 'examples/taskboard/frontend/dist');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };
const sample = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://127.0.0.1').pathname;
  const target = resolve(staticRoot, '.' + (path === '/' ? '/index.html' : path));
  if (!target.startsWith(staticRoot + '/')) { response.writeHead(403).end(); return; }
  try {
    const content = await readFile(target);
    response.setHeader('Content-Type', (mime[extname(target)] || 'application/octet-stream') + '; charset=utf-8');
    response.end(content);
  } catch { response.writeHead(404).end(); }
});
await new Promise((done, fail) => { sample.once('error', fail); sample.listen(port + 1, '127.0.0.1', done); });
console.log(`README preview: http://127.0.0.1:${port}/preview.html?scene=home`);
console.log('Scenes: home, team, workspace, projects, assistants, skills, automations, industry, models, channels');
const close = async () => { sample.close(); await vite.close(); process.exit(0); };
process.on('SIGINT', close); process.on('SIGTERM', close);
