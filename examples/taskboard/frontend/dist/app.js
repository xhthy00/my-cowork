import { createHost } from "./sdk.js";
const appId = "cn.example.taskboard";
const host = createHost({ appId });

const status = document.getElementById("status");
const list = document.getElementById("tasks");
const form = document.getElementById("new-task");
const selected = new Set(JSON.parse(sessionStorage.getItem('selected') || '[]'));
const aiStatus = document.getElementById('ai-status');
const attached = [];
let latestTask = sessionStorage.getItem('ai-task');
const seenStatuses = new Map();

host.on('host.appearance', message => {
  document.documentElement.dataset.theme = message.theme;
});
host.on('host.ai.changed', message => {
  for (const task of message.tasks || []) updateTask(task);
});
function updateTask(task) {
  if (task.task_id !== latestTask) return;
  const before = seenStatuses.get(task.task_id);
  seenStatuses.set(task.task_id, task.status);
  aiStatus.textContent = ({NEW:'准备中',RUNNING:'正在处理',DONE:'已完成，可查看结果',FAILED:'执行失败，请查看详情',CANCELLED:'已停止；已完成的修改不会撤销',INTERRUPTED:'已中断，请检查实际记录'})[task.status] || task.status;
  if (before !== task.status && ['DONE','FAILED','CANCELLED'].includes(task.status)) void refresh();
}
if (latestTask) void host.ai.getTask(latestTask).then(updateTask).catch(error => { aiStatus.textContent = error.message; });
window.addEventListener('pagehide', () => host.dispose());
const request = (method, path, body) => host.request(method, path, body);

async function refresh() {
  try {
    const result = await request("GET", "/tasks");
    const missing = [...selected].filter(id => !result.tasks.some(task => task.id === id));
    for (const id of missing) selected.delete(id);
    sessionStorage.setItem('selected', JSON.stringify([...selected]));
    list.replaceChildren();
    for (const task of result.tasks) {
      const item = document.createElement("li");
      const select = document.createElement('input');
      select.type = 'checkbox'; select.checked = selected.has(task.id);
      select.setAttribute('aria-label', '选择任务：' + task.title);
      select.addEventListener('change', () => {
        if (select.checked) selected.add(task.id); else selected.delete(task.id);
        sessionStorage.setItem('selected', JSON.stringify([...selected]));
        location.hash = '/tasks/' + [...selected].join(',');
        void host.navigation.setRoute(location.hash.slice(1)).catch(error => { status.textContent = error.message; });
      });
      if (task.done) item.classList.add("done");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = task.done;
      checkbox.setAttribute("aria-label", "完成任务：" + task.title);
      checkbox.addEventListener("change", async () => {
        try {
          await request("PATCH", "/tasks/" + task.id, { done: checkbox.checked });
          await refresh();
        } catch (error) {
          status.textContent = error.message;
        }
      });
      const title = document.createElement("span");
      title.textContent = task.title;
      item.append(select, checkbox, title);
      list.append(item);
    }
    status.textContent = missing.length ? '原来选中的任务已不存在，请重新选择业务内容。' : "";
  } catch (error) {
    status.textContent = error.message;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.getElementById("title");
  const title = input.value.trim();
  if (!title) return;
  try {
    await request("POST", "/tasks", { title });
    input.value = "";
    sessionStorage.removeItem('draft');
    await host.ui.setDirty(false);
    await refresh();
  } catch (error) {
    status.textContent = error.message;
  }
});

const titleInput = document.getElementById('title');
titleInput.value = sessionStorage.getItem('draft') || '';
titleInput.addEventListener('input', () => {
  sessionStorage.setItem('draft', titleInput.value);
  void host.ui.setDirty(!!titleInput.value.trim()).catch(() => {});
});
if (location.hash.startsWith('#/tasks/')) {
  selected.clear();
  for (const id of location.hash.slice(8).split(',')) if (Number(id) > 0) selected.add(Number(id));
}
document.getElementById('pick').addEventListener('click', async () => {
  try {
    const result = await host.files.pick(); attached.push(...result.files);
    document.getElementById('attachments').textContent = attached.map(file => file.name).join('、');
  } catch (error) { aiStatus.textContent = error.message; }
});
for (const [id, prompt] of Object.entries({ analyze: '分析所选任务的交付风险，引用实际任务数据，不要修改业务记录。', report: '根据所选任务生成本周工作报告，并保存为报告文件。', split: '为所选父任务提出下一步子任务，确认后创建。' })) {
  document.getElementById(id).addEventListener('click', async event => {
    if (!selected.size) { aiStatus.textContent = '请先选择要处理的任务'; return; }
    event.currentTarget.disabled = true;
    document.getElementById('open-ai').hidden = true;
    aiStatus.textContent = '正在发起…';
    try {
      const task = await host.ai.startTask({ prompt, context: { partition: 'local', selection: [...selected] },
        skills: id === 'analyze' ? ['risk-analysis'] : id === 'report' ? ['weekly-report'] : [],
        tools: id === 'split' ? ['list_tasks', 'create_subtask'] : ['list_tasks'], produce_file: id === 'report', files: attached.map(file => file.id) });
      latestTask = task.task_id; sessionStorage.setItem('ai-task', latestTask);
      aiStatus.textContent = '已开始，可继续处理业务。需要时打开 AI 详情。';
      document.getElementById('open-ai').hidden = false;
    } catch (error) { aiStatus.textContent = error.message; }
    finally { document.getElementById(id).disabled = false; document.getElementById('open-ai').hidden = !latestTask; }
  });
}
document.getElementById('open-ai').hidden = !latestTask;
document.getElementById('open-ai').addEventListener('click', () => {
  void host.ai.openTask(latestTask).catch(error => { aiStatus.textContent = error.message; });
});
void host.ui.setDirty(!!titleInput.value.trim()).catch(() => {});
void refresh();
