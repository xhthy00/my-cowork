/** Isolated screenshot fixture: real UI components, in-memory sample data, no backend/model calls. */
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from '../../../renderer/src/App';
import { usePageTabStore } from '../../../renderer/src/store/pageTab';
import { useIndustryNavigation } from '../../../renderer/src/store/industryNavigation';
import { useSessionsStore } from '../../../renderer/src/store/sessions';
import { useWorkforceStore } from '../../../renderer/src/store/workforce';
import '../../../renderer/src/styles/ds-tokens.css';
import '../../../renderer/src/styles/app.css';
import '../../../renderer/src/styles/markdown.css';
import '../../../renderer/src/styles/vivid-theme.css';
import '../../../renderer/src/styles/airy-theme.css';

const mode = new URLSearchParams(location.search).get('mode') || 'home';
const fakeBase = 'https://promotion.invalid';
const pluginOrigin = 'http://127.0.0.1:5189';
const tasks = [
  {id:1,title:'整理产品需求，确认本周交付范围',done:true},
  {id:2,title:'完成行业插件页面与业务 API 联调',done:false},
  {id:3,title:'检查数据迁移，准备安装验证',done:false},
  {id:4,title:'整理使用说明与演示材料',done:false},
];
const lifecycle = {busy:false,phase:'idle'};
const app = {id:'cn.example.taskboard',version:'1.0.0',generation:'promotion-demo',enabled:true,status:'ready',
  dev_url:pluginOrigin,manifest:{name:'任务管理样例',description:'任务记录、业务工具与随包行业技能',
  ui:{entry:'frontend/dist/index.html'},capabilities:{host_api:['ai','files','navigation','ui']}}};
const models = {activeId:'demo-deepseek',profiles:[{id:'demo-deepseek',name:'DeepSeek',provider:'openai',
  category:'cloud',model:'deepseek-chat',baseUrl:'https://api.deepseek.com',isValid:true}]};
const fetchOriginal = window.fetch.bind(window);
window.fetch = async (input,init) => {
  const url = typeof input === 'string' ? input : input instanceof Request ? input.url : String(input);
  if (!url.startsWith(fakeBase)) return fetchOriginal(input,init);
  let data: unknown = {};
  if (url.includes('/api/desktop/sessions')) data = {snapshot:null};
  else if (url.includes('/api/industry-ai-tasks') || url.includes('/api/automations')) data = {tasks:[]};
  else if (url.includes('/api/skills')) data = {skills:[]};
  else if (url.includes('/api/assistants')) data = {assistants:[]};
  return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
};
window.api = {
  getBackendUrl:async()=>fakeBase,
  getModels:async()=>models,
  onBackendReady:()=>()=>{},onBackendFailed:()=>()=>{},onIndustryStatus:()=>()=>{},
  industryList:async()=>({apps:[app],lifecycle}),
  industryRequest:async(_id,method,route)=>{
    if (method==='GET' && route==='/tasks') return {tasks};
    throw new Error('截图预览不执行业务写入');
  },
  getKey:async()=>null,
} as unknown as typeof window.api;
document.documentElement.classList.remove('dark');
document.documentElement.setAttribute('data-theme','light');
document.documentElement.style.setProperty('--ui-font-scale','1');
usePageTabStore.setState({workspaceView:'workspace',projectSidebarFolded:false,settingsOpen:false});
useSessionsStore.setState({sessions:[],activeId:null,messagesById:{},progressById:{}});
useSessionsStore.getState().createSession('新对话');
if (mode==='team') useWorkforceStore.getState().setSessionMode('workforce');
if (mode==='industry') {
  usePageTabStore.setState({workspaceView:'hub',hubTab:'workbench'});
  useIndustryNavigation.setState({activeId:app.id,dirty:false,routes:{[app.id]:'/tasks/2,3'}});
}
createRoot(document.getElementById('root')!).render(<App/>);
