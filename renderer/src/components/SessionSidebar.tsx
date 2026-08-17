const SESSIONS = [
  {
    id: "1",
    title: "生成 Q1 总结 PPT",
    status: "running",
    time: "刚刚",
  },
  {
    id: "2",
    title: "整理 Downloads 文件夹",
    status: "done",
    time: "14:20",
  },
  {
    id: "3",
    title: "GitHub 周报 → 飞书",
    status: "done",
    time: "周一 09:01",
  },
  {
    id: "4",
    title: "合同摘要 DOCX",
    status: "error",
    time: "昨天",
  },
  {
    id: "5",
    title: "example.com 截图",
    status: "done",
    time: "昨天",
  },
];

export default function SessionSidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <h2>会话</h2>
        <button className="icon-btn" type="button" title="新建会话">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>
      <div className="session-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        </svg>
        <input type="text" placeholder="搜索会话…" />
      </div>
      <div className="session-list">
        <div className="session-group">今天</div>
        {SESSIONS.map((s, i) => (
          <button
            key={s.id}
            className={`session-item ${i === 0 ? "active" : ""}`}
            type="button"
          >
            <span className="title">{s.title}</span>
            <span className="meta">
              <span className={`status ${s.status}`}>
                {s.status === "running" && "运行中"}
                {s.status === "done" && "已完成"}
                {s.status === "error" && "失败"}
              </span>
              <span>·</span>
              <span>{s.time}</span>
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}
