import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const out = path.join(root, 'docs/promotion/images');
const require = createRequire(import.meta.url);
let sharp;
try { sharp = require('sharp'); }
catch {
  if (!process.env.PROMOTION_NODE_MODULES) throw new Error('Set PROMOTION_NODE_MODULES to a directory containing sharp.');
  sharp = require(require.resolve('sharp', { paths: [process.env.PROMOTION_NODE_MODULES] }));
}
await fs.mkdir(out, { recursive: true });
const iconBytes = await fs.readFile(path.join(root, 'docs/screenshots/app-icon.png'));
const icon = `data:image/png;base64,${iconBytes.toString('base64')}`;
const team = `data:image/png;base64,${(await fs.readFile(path.join(root, 'design/brand/welcome-workforce-blue.png'))).toString('base64')}`;
await fs.copyFile(path.join(root, 'docs/screenshots/app-icon.png'), path.join(out, 'mycowork-logo.png'));
const C = { ink:'#233e50', muted:'#526c7e', blue:'#007ac5', line:'#c9e2f1', pale:'#e1f3ff', bg:'#f5fbff', green:'#167359' };
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
function text(x,y,s,size=28,weight=400,color=C.ink,anchor='start') {
  return `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}">${esc(s)}</text>`;
}
function rect(x,y,w,h,fill='white',radius=22,stroke=C.line,dash='') {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${radius}" fill="${fill}" stroke="${stroke}" stroke-width="2" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
}
function card(x,y,w,h,title,lines=[],fill='white',size=30) {
  return rect(x,y,w,h,fill)+text(x+26,y+44,title,size,650)+lines.map((line,i)=>text(x+26,y+85+i*34,line,24,400,C.muted)).join('');
}
function arrow(d,dashed=false,color=C.blue) {
  return `<path d="${d}" fill="none" stroke="${color}" stroke-width="3" ${dashed?'stroke-dasharray="8 8"':''} marker-end="url(#arrow)"/>`;
}
function chip(x,y,w,label) {
  return rect(x,y,w,46,C.pale,23,C.pale)+text(x+w/2,y+31,label,22,600,C.blue,'middle');
}
function shell(title,subtitle,body,height=1080) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="${height}" viewBox="0 0 1600 ${height}" role="img" aria-label="${esc(title)}">
  <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto-start-reverse"><path d="M1 1L8 5L1 9" fill="none" stroke="${C.blue}" stroke-width="1.5"/></marker><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#f5fbff"/><stop offset="1" stop-color="#e1f3ff"/></linearGradient></defs>
  <style>text{font-family:Inter,'PingFang SC','Hiragino Sans GB','Noto Sans CJK SC',sans-serif}</style>
  <rect width="1600" height="${height}" fill="url(#bg)"/>
  <image href="${icon}" x="56" y="38" width="62" height="62"/>
  ${text(136,80,'MyCoWork',34,700)}${text(1544,78,'开源桌面办公 Agent',23,500,C.muted,'end')}
  ${text(56,156,title,43,700)}${text(56,197,subtitle,24,400,C.muted)}
  ${body}
  <line x1="56" x2="1544" y1="${height-67}" y2="${height-67}" stroke="${C.line}"/>
  ${text(56,height-29,'MyCoWork轻松搞定每一件事！',23,600,C.blue)}${text(1544,height-29,'github.com/xhthy00/my-cowork',21,400,C.muted,'end')}
  </svg>`;
}
async function save(name,svg) {
  await fs.writeFile(path.join(out,`${name}.svg`),svg);
  await sharp(Buffer.from(svg)).png().toFile(path.join(out,`${name}.png`));
  console.log(`${name}: SVG + PNG`);
}

await save('01-cover', shell('给业务装上 AI 团队','技术栈 → 功能点 → 行业工作台',
  text(70,342,'你的桌面 AI 工作台',57,750)+
  text(70,409,'办公文件交付 · 多智能体协同',30,500,C.muted)+
  text(70,456,'业务页面、数据与工具一起接入',30,500,C.muted)+
  chip(70,512,145,'Word')+chip(235,512,145,'Excel')+chip(400,512,145,'PPT')+
  rect(70,614,650,130,'white',24)+text(100,660,'Electron · React · FastAPI',29,650)+text(100,708,'LangGraph · Skills · MCP',29,650,C.blue)+
  `<image href="${team}" x="755" y="240" width="790" height="527"/>`,900));

let arch = rect(56,230,1110,738,'#edf7fd',28)+text(82,270,'本机桌面应用',25,650,C.blue);
arch += card(82,298,715,112,'React + TypeScript',['对话 · 任务进度 · 文件预览 · 行业工作台']);
arch += card(821,298,319,112,'Electron',['启动后端 · 系统凭据'], 'white',28);
arch += arrow('M440 410V474')+text(460,451,'HTTP + SSE',22,500,C.blue);
arch += arrow('M981 410V474')+text(1000,451,'启动 / 认证',21,500,C.blue);
arch += card(82,484,1058,164,'FastAPI + LangGraph',['任务编排 · 单智能体 / Workforce · 工具调用','执行事件 · 审批与 Trace · 行业业务 API'],'#fff');
arch += arrow('M260 648V705')+arrow('M611 648V705')+arrow('M962 648V705');
arch += card(82,716,336,140,'办公工具',['OfficeCLI','Word · Excel · PPT'],'white',28);
arch += card(443,716,336,140,'连接与浏览',['MCP · Playwright'],'white',28);
arch += card(804,716,336,140,'行业插件',['Python API · Agent 工具'],'white',28);
arch += rect(82,880,1058,70,'white',18)+text(611,925,'本机工作区  /  SQLite  /  行业应用数据',28,550,C.ink,'middle');
arch += card(1210,298,334,162,'可选云模型',['OpenAI · Anthropic','DeepSeek · 通义等'],'white',28);
arch += card(1210,618,334,162,'可选本地推理',['Ollama · LM Studio','vLLM 等'],'white',28);
arch += arrow('M1140 534H1179V379H1202')+arrow('M1140 590H1179V698H1202');
arch += text(1208,514,'模型请求与响应',24,550,C.blue);
arch += text(1210,842,'选择云模型时，相关任务内容',20,400,C.muted)+text(1210,873,'会发送给所选服务。',20,400,C.muted);
await save('02-architecture',shell('技术架构：从桌面交互到本机执行','Electron 管理桌面能力，FastAPI 与 LangGraph 组织任务和工具。',arch,1080));

let work = card(56,242,333,116,'01  用户需求',['明确材料与交付要求']);
work += card(441,242,333,116,'02  Planner',['拆解子任务与依赖']);
work += card(826,242,333,116,'03  用户确认',['查看并确认计划']);
work += card(1211,242,333,116,'04  Coordinator',['选择可以执行的工作'],'#e1f3ff',28);
work += arrow('M389 300H429')+arrow('M774 300H814')+arrow('M1159 300H1199');
work += arrow('M1378 358V406H800V447');
work += rect(56,452,1488,302,'#edf7fd',28)+text(88,497,'Worker 分工',31,650,C.blue)+text(1510,496,'按依赖就绪调度 · 独立工作可并行',24,500,C.muted,'end');
work += card(90,533,444,167,'浏览 Worker',['网页交互 · 资料相关工作','使用任务授权的浏览工具']);
work += card(578,533,444,167,'文档 Worker',['文档处理 · 文件生成','使用任务授权的办公工具']);
work += card(1066,533,444,167,'开发 Worker',['代码 · 脚本类任务','使用任务授权的开发工具']);
work += arrow('M800 754V805');
work += card(391,816,818,117,'05  汇总与交付',['结果整合 · 文件落盘 · 任务进度同步'],'white');
work += `<path d="M1290 700V730H1518V414H1398V364" stroke="${C.blue}" stroke-width="2.5" fill="none" stroke-dasharray="8 8" marker-end="url(#arrow)"/>`;
work += text(1400,793,'失败时重试',23,550,C.blue,'middle')+text(1400,828,'或重新规划',23,550,C.blue,'middle');
await save('03-workforce',shell('多智能体协同：有计划，也有依赖','简单任务使用单智能体；复杂任务用 Workforce 组织分工。',work,1060));

let industry = rect(56,237,1488,179,'#e1f3ff',28)+text(88,281,'一个行业应用包',29,700,C.blue);
const parts=[['业务页面','列表 · 表单 · 导航'],['业务 API 与数据','Python · SQLite · 迁移'],['Agent 工具','查询 · 写入 · 范围校验'],['行业 Skills','方法 · 模板 · 参考资料']];
parts.forEach(([a,b],i)=>{industry+=rect(88+i*362,301,338,87,'white',16)+text(110+i*362,337,a,27,650)+text(110+i*362,371,b,22,400,C.muted);});
industry += text(56,480,'从选中业务记录，到返回实际结果',33,700);
const steps=[['01','选择业务记录','用户选择任务与范围'],['02','宿主 SDK 桥接','传递上下文与工具集合'],['03','AI 分析与调用','加载所选行业技能'],['04','业务工具执行','校验范围 · 写入需确认']];
steps.forEach(([n,a,b],i)=>{const x=56+i*385;industry+=rect(x,520,333,161,'white',22)+text(x+24,558,n,23,700,C.blue)+text(x+24,603,a,27,650)+text(x+24,645,b,22,400,C.muted);if(i<3)industry+=arrow(`M${x+333} 602H${x+374}`);});
industry += arrow('M1378 681V729H800V771');
industry += rect(56,782,1488,165,'white',25)+text(90,826,'执行结果回到业务流程',31,700)+text(90,871,'业务页面刷新记录  ·  AI 记录查看状态与事件  ·  文件产物可打开',27,400,C.muted);
industry += chip(90,890,380,'样例：任务分析 / Markdown 周报')+chip(496,890,344,'样例：确认后创建子任务');
industry += text(56,1001,'开发路径：模板 → 本地预览 → 校验打包 → ZIP 安装 → 更新与数据迁移',26,550,C.blue);
await save('04-industry-workbench',shell('行业工作台：页面、数据、工具与技能一起接入','业务页面提供上下文，AI 组织分析，业务工具完成允许的操作。',industry,1130));
