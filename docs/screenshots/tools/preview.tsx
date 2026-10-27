/** Real components with explicit sample data. Never connects to a real backend. */
import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import App from '../../../renderer/src/App';
import { usePageTabStore } from '../../../renderer/src/store/pageTab';
import { useIndustryNavigation } from '../../../renderer/src/store/industryNavigation';
import { useSessionsStore } from '../../../renderer/src/store/sessions';
import { useSpacesStore } from '../../../renderer/src/store/spaces';
import { useSessionStore } from '../../../renderer/src/store/session';
import { useWorkforceStore } from '../../../renderer/src/store/workforce';
import { usePreviewStore } from '../../../renderer/src/store/preview';
import '../../../renderer/src/styles/ds-tokens.css';
import '../../../renderer/src/styles/app.css';
import '../../../renderer/src/styles/markdown.css';
import '../../../renderer/src/styles/vivid-theme.css';
import '../../../renderer/src/styles/airy-theme.css';

const scene = new URLSearchParams(location.search).get('scene') || 'home';
const base = 'https://readme.invalid';
const sampleTime = new Date('2026-10-27T09:00:00+08:00').getTime();
const catalog = await fetch('/fixture/catalog.json').then(response => response.json());
const noEvents = () => () => {};
const app = { id: 'cn.example.taskboard', version: '1.0.0', enabled: true, status: 'ready', generation: 'readme-example',
  dev_url: `http://127.0.0.1:${Number(location.port) + 1}`, manifest: { name: '任务管理样例', description: '任务记录、业务工具与随包技能，在业务页面中使用 AI。',
    ui: { entry: 'frontend/dist/index.html' }, capabilities: { host_api: ['ai', 'files', 'navigation', 'ui'] } } };
const tasks = [{ id: 1, title: '核对本周项目交付清单', done: true },
  { id: 2, title: '完成业务页面与 AI 工具联调', done: false },
  { id: 3, title: '整理客户反馈，形成项目周报', done: false },
  { id: 4, title: '检查安装包与数据恢复流程', done: false }];
const automations = [
  ['daily', '每日行业信息简报', '工作日 09:00', '0 9 * * 1-5', '收集公开行业信息，整理来源链接并保存摘要。'],
  ['weekly', '项目周报汇总', '每周五 17:30', '30 17 * * 5', '汇总工作区的项目记录，生成本周进展与下周计划。'],
  ['check', '交付资料检查', '每天 18:00', '0 18 * * *', '检查指定工作区的交付文件，记录缺项与需要人工处理的事项。'],
].map(([id, title, schedule_label, cron, instructions], i) => ({ id, title, schedule_label, instructions,
  schedule: { kind: 'cron', cron, timezone: 'Asia/Shanghai' }, source: 'user', enabled: i !== 2,
  next_run: new Date(['2026-10-28T09:00:00+08:00', '2026-10-30T17:30:00+08:00', '2026-10-28T18:00:00+08:00'][i]).getTime() / 1000,
  last_run: new Date(['2026-10-27T09:00:00+08:00', '2026-10-23T17:30:00+08:00', '2026-10-26T18:00:00+08:00'][i]).getTime() / 1000,
  last_status: 'ok', run_count: 4 + i, unseen_runs: 0, unseen_failed: false, notify_on_completion: true,
  active_run: null, always_allowed_tools: [], always_allowed_commands: [], auto_approve_commands: false }));
const channels = ['telegram', 'lark', 'dingtalk', 'weixin'].map(id => ({ plugin_id: id, type: id, name: id,
  coming_soon: ['telegram', 'dingtalk'].includes(id), enabled: false, connected: false, has_token: false, active_users: 0 }));
const models = { activeId: 'example-model', profiles: [{ id: 'example-model', name: 'DeepSeek', provider: 'openai_compat',
  presetId: 'deepseek', category: 'cloud_byok', model: 'deepseek-chat', baseUrl: 'https://api.deepseek.com/v1', isValid: true },
  { id: 'example-local', name: 'Ollama', provider: 'ollama', category: 'local', model: 'qwen3:8b', baseUrl: 'http://127.0.0.1:11434/v1', isValid: true }] };
const report = '# 项目周报\n\n> 界面演示资料 · 示例数据\n\n## 本周进展\n\n| 工作事项 | 状态 | 交付结果 |\n| --- | --- | --- |\n| 需求整理 | 已完成 | 交付范围与优先级清单 |\n| 业务联调 | 已完成 | 页面与业务工具联通 |\n| 资料检查 | 进行中 | 完善验收记录 |\n\n## 风险与待办\n\n- 资料归档仍需补齐两项附件。\n- 数据恢复流程安排在正式更新前演练。\n\n## 下周计划\n\n1. 完成剩余资料核对。\n2. 演示业务页面中的 AI 风险分析。\n3. 整理项目验收说明。';

const originalFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const url = typeof input === 'string' ? input : input instanceof Request ? input.url : String(input);
  if (!url.startsWith(base)) return originalFetch(input, init);
  const path = new URL(url).pathname;
  const method = init?.method || (input instanceof Request ? input.method : 'GET');
  let data: unknown = {};
  if (path === '/api/desktop/sessions') data = { snapshot: null };
  else if (path === '/api/assistants') data = { assistants: catalog.assistants };
  else if (path === '/api/skills') data = { skills: catalog.skills };
  else if (path === '/api/automations') data = { tasks: automations };
  else if (path === '/api/industry-ai-tasks') data = { tasks: [] };
  else if (path === '/api/channel/plugins') data = channels;
  else if (path.includes('/api/channel/')) data = [];
  else if (path === '/api/model/info') data = { context_limit: 128000, model: 'deepseek-chat' };
  else if (path === '/api/memory/settings') data = { enabled: true, allow_agent_writes: true, user_rules: '' };
  else if (path.includes('/overlays')) data = { overlays: [] };
  else if (path.includes('/libraries')) data = { libraries: [] };
  else if (path === '/api/mcp') data = { servers: [] };
  if (method !== 'GET' && path !== '/api/desktop/sessions') {
    return new Response(JSON.stringify({ detail: '文档截图预览不执行真实操作' }), { status: 403 });
  }
  return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
};
window.api = {
  getBackendUrl: async () => base, getModels: async () => models,
  getUpdaterStatus: async () => ({ state: 'idle', currentVersion: '0.1.6' }), onUpdaterStatus: noEvents,
  getKeepAwake: async () => ({ enabled: false, supported: true }),
  onBackendReady: noEvents, onBackendFailed: noEvents, onIndustryStatus: noEvents, onModelsChanged: noEvents,
  industryList: async () => ({ apps: [app], lifecycle: { busy: false, phase: 'idle' } }),
  industryRequest: async (_id, method, path) => {
    if (method === 'GET' && path === '/tasks') return { tasks };
    if (method === 'GET' && path === '/tasks/count') return { count: tasks.length };
    throw new Error('文档截图预览不执行业务写入');
  },
  getKey: async () => null, readTextFile: async () => ({ content: report }),
  ipcOpenPath: async () => {}, getCdpBrowsers: async () => [],
} as unknown as typeof window.api;

document.documentElement.classList.remove('dark');
document.documentElement.setAttribute('data-theme', 'light');
document.documentElement.style.setProperty('--ui-font-scale', '1');
usePageTabStore.setState({ workspaceView: 'workspace', projectSidebarFolded: false, projectHistoryCollapsed: false,
  settingsOpen: false, previewOpen: false, sidePanelVisible: true });
useIndustryNavigation.setState({ activeId: null, dirty: false, routes: {} });
useSpacesStore.setState({ activeSpaceId: 'space-local', spaces: [{ id: 'space-local', name: '办公演示空间', sourceType: 'blank', rootPath: null,
  createdAt: sampleTime, updatedAt: sampleTime }] });
useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {}, progressById: {} });
for (const [i, title] of ['项目资料整理', '业务需求分析', '每周工作简报'].entries()) {
  useSessionsStore.getState().createSession(title, { id: `readme-history-${i}`, background: true,
    createdAt: sampleTime - (i + 1) * 86400000, updatedAt: sampleTime - (i + 1) * 86400000 });
}
useSessionsStore.getState().createSession(scene === 'workspace' ? '项目周报与交付资料' : '新任务', { id: 'readme-current' });
if (scene === 'team') useWorkforceStore.getState().setSessionMode('workforce');
if (scene === 'workspace') {
  useSessionStore.setState({ messages: [{ id: 'request', role: 'user', content: '把项目进展整理成周报，列出风险和下周计划。', createdAt: sampleTime },
    { id: 'answer', role: 'assistant', content: '已整理项目周报，包含本周进展、风险与待办、下周计划。\n\n交付文件可在右侧预览，后续可以继续补充内容或调整结构。',
      artifacts: [{ name: '项目周报.md', path: '/demo/项目周报.md', kind: 'file' }], createdAt: sampleTime + 60000 }], runStatus: 'done' });
  usePreviewStore.getState().openFile('/demo/项目周报.md');
  usePageTabStore.setState({ previewOpen: true, sidePanelVisible: false });
}
if (scene === 'projects') usePageTabStore.setState({ workspaceView: 'hub', hubTab: 'home', homeSection: 'projects' });
if (scene === 'assistants' || scene === 'skills') usePageTabStore.setState({ workspaceView: 'hub', hubTab: 'agents', agentsSection: scene === 'skills' ? 'skills' : 'sub-agents' });
if (scene === 'automations') usePageTabStore.setState({ workspaceView: 'hub', hubTab: 'home', homeSection: 'triggers' });
if (scene === 'industry') {
  usePageTabStore.setState({ workspaceView: 'hub', hubTab: 'workbench' });
  useIndustryNavigation.setState({ activeId: app.id, dirty: false, routes: {} });
}
if (scene === 'models' || scene === 'channels') usePageTabStore.setState({ settingsOpen: true, settingsSection: scene === 'models' ? 'model' : 'channels' });
createRoot(document.getElementById('root')!).render(<><App /><div style={{ position: 'fixed', bottom: 3, right: 16, fontSize: 10, color: '#64748b', pointerEvents: 'none' }}>README · 当前源码界面 / 示例数据</div></>);
