#!/usr/bin/env node
/* Local author workflow; the installer remains the single package validator. */
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const readline = require('node:readline');
const net = require('node:net');
const { spawn, spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const REPO = path.resolve(__dirname, '..');
const PYTHON = path.join(REPO, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const PACKER = path.join(REPO, 'scripts/pack-industry-app.py');

function checkedDirectory(directory) {
  const absolute = path.resolve(directory);
  for (let item = absolute; ; item = path.dirname(item)) {
    if (fs.existsSync(item) && (fs.lstatSync(item).isSymbolicLink() || fs.realpathSync(item).toLowerCase() !== item.toLowerCase())) throw new Error('不支持链接目录：' + item);
    if (path.dirname(item) === item) break;
  }
  return absolute;
}
function dependencyVersion(name) { return require(path.join(REPO, 'node_modules', name, 'package.json')).version; }
function initProject(destination, id, name) {
  if (!/^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$/.test(id || '')) throw new Error('ID 必须为小写反向域名，例如 cn.example.inventory');
  if (!name?.trim() || name.trim().length > 80) throw new Error('名称须为 1–80 个字符');
  const project = checkedDirectory(destination);
  if (fs.existsSync(project) && fs.readdirSync(project).length) throw new Error('目标目录非空，不能覆盖');
  const replacements = {
    __APP_ID__: id, __PYTHON_PACKAGE__: 'mcapp_' + id.replaceAll('.', '_'),
    __APP_NAME_JSON__: JSON.stringify(name.trim()), __APP_NAME_TEXT__: name.trim(),
    __APP_NAME_HTML__: name.trim().replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char])),
    __SDK_PATH__: path.join(REPO, 'packages/app-sdk').replaceAll('\\', '/'),
    __REACT_VERSION__: dependencyVersion('react'), __REACT_DOM_VERSION__: dependencyVersion('react-dom'),
    __REACT_TYPES_VERSION__: dependencyVersion('@types/react'), __REACT_DOM_TYPES_VERSION__: dependencyVersion('@types/react-dom'),
    __REACT_PLUGIN_VERSION__: dependencyVersion('@vitejs/plugin-react'), __VITE_VERSION__: dependencyVersion('vite'), __TS_VERSION__: dependencyVersion('typescript'),
  };
  const render = content => content.replace(/__[A-Z_]+__/g, key => replacements[key] ?? key);
  function copy(source, target) {
    fs.mkdirSync(target, { recursive: true });
    for (const file of fs.readdirSync(source, { withFileTypes: true })) {
      const dest = path.join(target, render(file.name));
      if (file.isDirectory()) copy(path.join(source, file.name), dest);
      else fs.writeFileSync(dest, render(fs.readFileSync(path.join(source, file.name), 'utf8')));
    }
  }
  copy(path.join(REPO, 'templates/industry-app'), project);
  fs.writeFileSync(path.join(project, '.gitignore'), 'frontend/node_modules/\nfrontend/dist/\n__pycache__/\n*.pyc\n');
  return project;
}
function runPython(args) {
  if (!fs.existsSync(PYTHON)) throw new Error('缺少宿主 backend/.venv，请先按开发指南准备宿主 Python 环境');
  const result = spawnSync(PYTHON, [PACKER, ...args, '--json'], {
    cwd: REPO, env: { ...process.env, MY_COWORK_APP_VERSION: require('../package.json').version, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' }, encoding: 'utf8', windowsHide: true, maxBuffer: 2 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error((result.stderr || '包检查失败').trim());
  return JSON.parse(result.stdout);
}
function buildFrontend(project) {
  const frontend = path.join(project, 'frontend');
  if (!fs.existsSync(path.join(frontend, 'package.json'))) return; // Existing static plugin.
  if (!fs.existsSync(path.join(frontend, 'node_modules'))) throw new Error('缺少插件前端依赖，请在 frontend 目录执行 npm install');
  const npmCli = process.env.npm_execpath || path.join(path.dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js');
  if (!fs.existsSync(npmCli)) throw new Error('找不到 npm，请通过 npm run app -- pack/dev 调用，或准备包含 npm 的 Node 环境');
  const result = spawnSync(process.execPath, [npmCli, 'run', 'build'], { cwd: frontend, stdio: 'inherit', windowsHide: true });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error('前端构建失败，本次不生成候选或 ZIP；修正后重试');
}
function developmentDirectory(project, packageTest = false) {
  const identity = fs.realpathSync(checkedDirectory(project));
  const digest = crypto.createHash('sha256').update(process.platform === 'win32' ? identity.toLowerCase() : identity).digest('hex').slice(0, 24);
  // A short, explicit home path avoids Windows packaged-app LocalAppData
  // virtualization and keeps managed snapshots below common path limits.
  return path.join(os.homedir(), '.mycowork-app-dev', digest, packageTest ? 'package-test' : 'source');
}
function developmentEnv(inherited, directory) {
  const env = { ...inherited };
  for (const key of Object.keys(env)) {
    if (/^(MY_COWORK_|OPENAI_|ANTHROPIC_|LARK_|WEIXIN_|IMA_|BOCHA_|BRAVE_|TAVILY_|EXA_|SEARXNG_|VITE_)/i.test(key) || /(?:API_KEY|AUTH_TOKEN|ACCESS_TOKEN|SECRET|PASSWORD)$/i.test(key) || ['ELECTRON_RUN_AS_NODE', 'NODE_OPTIONS', 'PYTHONPATH', 'PYTHONHOME'].includes(key)) delete env[key];
  }
  const backend = path.resolve(directory, 'backend');
  Object.assign(env, {
    MY_COWORK_APP_DEV: '1', MY_COWORK_USER_DATA_DIR: path.resolve(directory, 'electron'), MY_COWORK_DATA_DIR: backend,
    MY_COWORK_INDUSTRY_APPS_ROOT: path.join(backend, 'industry-apps'), MY_COWORK_SKILLS_ROOT: path.join(backend, 'skills'),
    MY_COWORK_SKILLS_CONFIG: path.join(backend, 'skills-config.json'), MY_COWORK_MCP_JSON: path.join(backend, 'mcp.json'),
    MY_COWORK_CHANNELS_DB: path.join(backend, 'channels.db'), MY_COWORK_SCHEDULER_DB: path.join(backend, 'scheduler.db'),
    MY_COWORK_ENABLE_SCHEDULER: '0', MY_COWORK_CHANNEL_AUTOSTART: '0', MY_COWORK_DISABLE_CHANNELS: '1',
    MY_COWORK_CREDENTIAL_SCOPE: crypto.createHash('sha256').update(path.resolve(directory)).digest('hex'),
  });
  return env;
}
function acquireSession(directory) {
  checkedDirectory(directory); fs.mkdirSync(directory, { recursive: true });
  const file = path.join(directory, 'session.lock');
  if (fs.existsSync(file)) {
    checkedDirectory(file);
    const previous = JSON.parse(fs.readFileSync(file, 'utf8'));
    try { process.kill(previous.pid, 0); throw new Error('此开发目录已有运行实例，请先退出原终端'); }
    catch (error) { if (error.code !== 'ESRCH') throw error; }
    fs.unlinkSync(file);
  }
  const token = crypto.randomUUID();
  fs.writeFileSync(file, JSON.stringify({ pid: process.pid, token }), { flag: 'wx' });
  return () => { if (fs.existsSync(file) && JSON.parse(fs.readFileSync(file, 'utf8')).token === token) fs.unlinkSync(file); };
}
function showInspection(result) {
  console.log(`检查环境：宿主 ${require('../package.json').version} · ${process.platform}/${process.arch}`);
  console.log(`${result.manifest.name} ${result.manifest.version} · ${result.file_count} 个文件 · ${result.expanded_bytes} 字节（展开）`);
  for (const file of result.files) console.log('  ' + file);
  console.log('检查通过仅表示当前宿主/平台接受此包；业务与模型效果须实际验收。');
}

async function dev(project, packageTest = false) {
  project = checkedDirectory(project);
  const directory = developmentDirectory(project, packageTest);
  const release = acquireSession(directory);
  let server, child, watcher, input;
  let stopping = false, reloading = false, closing, lastStatus;
  const logPath = path.join(directory, 'development.log');
  const log = fs.createWriteStream(logPath, { flags: 'a' });
  const zip = path.join(directory, 'candidate.zip');
  async function candidate() {
    if (!fs.existsSync(path.join(project, 'frontend/dist/index.html'))) buildFrontend(project);
    return runPython([project, '-o', zip, '--replace']);
  }
  function close() {
    if (closing) return closing;
    stopping = true; watcher?.close(); input?.close();
    closing = (async () => {
      if (child?.pid && child.exitCode === null) {
        console.log('正在等待本实例已有工作结束；数据和日志会保留。');
        const exited = new Promise(resolve => child.once('exit', resolve));
        if (child.connected) child.send({ command: 'quit' });
        await exited;
      }
      await server?.close(); log.end(); release();
    })();
    return closing;
  }
  try {
    require.resolve('electron');
    const compiled = spawnSync(process.execPath, [require.resolve('typescript/bin/tsc')], { cwd: REPO, stdio: 'inherit', windowsHide: true });
    if (compiled.status !== 0) throw new Error('宿主 Electron 编译失败');
    if (!fs.existsSync(path.join(REPO, 'dist-renderer/index.html'))) {
      const build = spawnSync(process.execPath, [path.join(REPO, 'node_modules/vite/bin/vite.js'), 'build'], { cwd: REPO, stdio: 'inherit', windowsHide: true });
      if (build.status !== 0) throw new Error('宿主界面构建失败');
    }
    const env = developmentEnv(process.env, directory);
    fs.mkdirSync(env.MY_COWORK_DATA_DIR, { recursive: true });
    if (!fs.existsSync(env.MY_COWORK_MCP_JSON)) fs.writeFileSync(env.MY_COWORK_MCP_JSON, '{"mcpServers":{}}');
    if (!packageTest) {
      const inspection = await candidate();
      const frontend = path.join(project, 'frontend');
      const vite = await import(pathToFileURL(path.join(REPO, 'node_modules/vite/dist/node/index.js')).href);
      const isVite = fs.existsSync(path.join(frontend, 'package.json'));
      const reservation = net.createServer();
      await new Promise((resolve, reject) => { reservation.once('error', reject); reservation.listen(0, '127.0.0.1', resolve); });
      const allocatedPort = reservation.address().port;
      await new Promise((resolve, reject) => reservation.close(error => error ? reject(error) : resolve()));
      server = await vite.createServer({
        cacheDir: path.join(directory, 'vite-cache'),
        root: isVite ? frontend : path.join(frontend, 'dist'), configFile: isVite ? undefined : false,
        server: { host: '127.0.0.1', port: allocatedPort, strictPort: true, cors: false,
          fs: { strict: true, allow: [frontend, path.join(REPO, 'packages/app-sdk')] } },
        plugins: isVite ? [] : [{ name: 'static-app-refresh', handleHotUpdate(ctx) { ctx.server.ws.send({ type: 'full-reload' }); return []; } }],
      });
      await server.listen();
      const port = server.httpServer.address().port;
      Object.assign(env, { MY_COWORK_DEV_APP_ID: inspection.manifest.id, MY_COWORK_DEV_URL: `http://127.0.0.1:${port}`, MY_COWORK_DEV_ZIP: zip });
      watcher = fs.watch(project, { recursive: true }, (_event, file) => {
        const relative = String(file || '').replaceAll('\\', '/');
        if ((relative.startsWith('backend/') && !relative.includes('__pycache__')) || relative.startsWith('skills/') || relative === 'mycowork-app.yaml') console.log('源码有变化，保存页面内容后输入 r 重新加载。');
      });
    } else {
      // Package-test uses isolated storage/credentials but never development paths.
      delete env.MY_COWORK_APP_DEV;
      env.MY_COWORK_APP_PACKAGE_TEST = '1';
    }
    env.MY_COWORK_DEV_CONTROL = '1';
    console.log(`开发目录：${directory}\n详细日志：${logPath}\n正在启动；请在此独立实例配置模型。r 重载，c 取消等待，q 退出。`);
    child = spawn(require('electron'), ['dist-electron/main.js'], { cwd: REPO, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe', 'ipc'] });
    child.stdout.pipe(log, { end: false }); child.stderr.pipe(log, { end: false });
    child.on('error', error => { console.error(error.message); void close(); });
    child.on('message', message => {
      if (message.phase) {
        const status = message.message || ({ committed: '插件可用', pending_activation: '请配置模型后输入 r 继续', draining: '正在等待已有工作结束', failed: '操作失败，请查看日志', recovery_required: '需要恢复，请查看工作台' }[message.phase] || message.phase);
        if (status !== lastStatus) console.log(status);
        lastStatus = status;
      }
    });
    input = readline.createInterface({ input: process.stdin });
    input.on('line', async line => {
      const command = line.trim().toLowerCase();
      if (command === 'q') return void close();
      if (command === 'c') return child?.send({ command: 'cancel' });
      if (command !== 'r' || stopping) return;
      if (reloading) return console.log('本次重载尚未完成，请等待或输入 c 取消等待。');
      reloading = true;
      try {
        if (!packageTest) { await candidate(); child.send({ command: 'reload' }); }
        else child.send({ command: 'restart' });
      } catch (error) { console.error(error.message); console.log('原运行状态保持；修复后再输入 r。'); reloading = false; }
    });
    child.on('message', message => { if (message.done) reloading = false; });
    input.on('close', () => { if (!stopping) void close(); });
    const signal = () => { void close(); };
    process.once('SIGINT', signal); process.once('SIGTERM', signal);
    await new Promise((resolve, reject) => { child.once('exit', resolve); child.once('error', reject); });
    process.removeListener('SIGINT', signal); process.removeListener('SIGTERM', signal);
    await close();
  } catch (error) { await close(); throw error; }
}

async function main(args) {
  const [command, destination, ...rest] = args;
  const option = name => { const index = rest.indexOf(name); return index < 0 ? undefined : rest[index + 1]; };
  if (!destination || !['init', 'dev', 'validate', 'pack'].includes(command)) throw new Error('用法：mycowork-app init|dev|validate|pack <目录或 ZIP>；init --id ID --name 名称；pack -o 输出.zip；dev --package-test');
  if (command === 'init') {
    let id = option('--id'), name = option('--name');
    if ((!id || !name) && process.stdin.isTTY) {
      const prompt = readline.createInterface({ input: process.stdin, output: process.stdout });
      const ask = text => new Promise(resolve => prompt.question(text, resolve));
      id ||= await ask('插件 ID（如 cn.example.inventory）：'); name ||= await ask('名称：'); prompt.close();
    }
    const project = initProject(destination, id, name);
    console.log(`已创建 ${project}\n下一步：在 frontend 执行 npm install，然后运行 mycowork-app dev "${project}"。`);
  } else if (command === 'dev') await dev(destination, rest.includes('--package-test'));
  else if (command === 'validate') showInspection(runPython([path.resolve(destination), '--check']));
  else {
    const output = option('-o') || option('--output');
    if (!output) throw new Error('请用 -o 指定源码目录之外的 ZIP 输出路径');
    if (fs.existsSync(path.resolve(output))) throw new Error('输出已存在，请选择新路径；默认不覆盖');
    const project = checkedDirectory(destination);
    buildFrontend(project); const result = runPython([project, '-o', path.resolve(output)]);
    showInspection(result); console.log(`已生成 ${result.output}`);
  }
}
module.exports = { initProject, developmentEnv, developmentDirectory, acquireSession, dev, main };
if (require.main === module) main(process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1; });
