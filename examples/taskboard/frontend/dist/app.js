const channel = "mycowork-app/v1";
const appId = "cn.example.taskboard";
const bridgeToken = new URLSearchParams(location.search).get("bridge");
const pending = new Map();
const status = document.getElementById("status");
const list = document.getElementById("tasks");
const form = document.getElementById("new-task");

window.addEventListener("message", (event) => {
  if (event.source !== window.parent) return;
  const message = event.data;
  if (!message || message.channel !== channel || message.appId !== appId || message.bridgeToken !== bridgeToken || message.type !== "response") return;
  const item = pending.get(message.id);
  if (!item) return;
  pending.delete(message.id);
  if (message.ok) item.resolve(message.data);
  else item.reject(new Error(message.error || "请求失败"));
});

function request(method, path, body) {
  if (!bridgeToken) return Promise.reject(new Error("请从 MyCowork 工作台打开此应用"));
  return new Promise((resolve, reject) => {
    const id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + "-" + String(Math.random());
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error("宿主响应超时"));
    }, 15000);
    pending.set(id, {
      resolve: (value) => { clearTimeout(timer); resolve(value); },
      reject: (error) => { clearTimeout(timer); reject(error); },
    });
    window.parent.postMessage({ channel, appId, bridgeToken, id, type: "request", operation: "app.request", method, path, body }, "*");
  });
}

async function refresh() {
  try {
    const result = await request("GET", "/tasks");
    list.replaceChildren();
    for (const task of result.tasks) {
      const item = document.createElement("li");
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
      item.append(checkbox, title);
      list.append(item);
    }
    status.textContent = "";
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
    await refresh();
  } catch (error) {
    status.textContent = error.message;
  }
});

void refresh();
