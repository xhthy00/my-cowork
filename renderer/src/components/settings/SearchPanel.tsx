import { Eye, EyeOff } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { SettingsField } from "@/components/settings/SettingsField";

const ACCOUNTS = {
  provider: "search:provider",
  bocha: "search:bocha",
  brave: "search:brave",
  tavily: "search:tavily",
  exa: "search:exa",
  searxng: "search:searxng",
} as const;

export default function SearchPanel() {
  const [provider, setProvider] = useState("");
  const [bocha, setBocha] = useState("");
  const [brave, setBrave] = useState("");
  const [tavily, setTavily] = useState("");
  const [exa, setExa] = useState("");
  const [searxng, setSearxng] = useState("");
  const [show, setShow] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!window.api?.getKey) return;
      const [p, a, b, t, e, s] = await Promise.all([
        window.api.getKey(ACCOUNTS.provider),
        window.api.getKey(ACCOUNTS.bocha),
        window.api.getKey(ACCOUNTS.brave),
        window.api.getKey(ACCOUNTS.tavily),
        window.api.getKey(ACCOUNTS.exa),
        window.api.getKey(ACCOUNTS.searxng),
      ]);
      if (cancelled) return;
      setProvider(p || "");
      setBocha(a || "");
      setBrave(b || "");
      setTavily(t || "");
      setExa(e || "");
      setSearxng(s || "");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function save() {
    if (!window.api?.setKey) return;
    await Promise.all([
      window.api.setKey(ACCOUNTS.provider, provider.trim()),
      window.api.setKey(ACCOUNTS.bocha, bocha.trim()),
      window.api.setKey(ACCOUNTS.brave, brave.trim()),
      window.api.setKey(ACCOUNTS.tavily, tavily.trim()),
      window.api.setKey(ACCOUNTS.exa, exa.trim()),
      window.api.setKey(ACCOUNTS.searxng, searxng.trim()),
    ]);
    setStatus("已保存。重启后端后生效。未填 Key 时将使用 DuckDuckGo 兜底。");
    if (window.api.restartBackend) {
      await window.api.restartBackend();
    }
  }

  const type = show ? "text" : "password";

  return (
    <div>
      <h3>检索</h3>
      <p className="panel-desc">
        内置 web_search 按博查 → Brave → Tavily → Exa → SearXNG 顺序尝试，最后用免 Key 的 DuckDuckGo。
        Key 存系统钥匙串，不写入仓库配置。
      </p>
      <div className="form-group" style={{ display: "grid", gap: 12, maxWidth: 480 }}>
        <label className="flex flex-col gap-1 text-body-sm">
          <span className="font-bold">首选 provider（可选）</span>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="h-10 rounded-xl border px-3"
          >
            <option value="">自动</option>
            <option value="bocha">博查</option>
            <option value="brave">Brave</option>
            <option value="tavily">Tavily</option>
            <option value="exa">Exa</option>
            <option value="searxng">SearXNG</option>
            <option value="ddgs">DuckDuckGo</option>
          </select>
        </label>
        <SettingsField
          title="博查 API Key"
          type={type}
          value={bocha}
          onChange={(e) => setBocha(e.target.value)}
          autoComplete="off"
        />
        <SettingsField
          title="Brave API Key"
          type={type}
          value={brave}
          onChange={(e) => setBrave(e.target.value)}
          autoComplete="off"
        />
        <SettingsField
          title="Tavily API Key"
          type={type}
          value={tavily}
          onChange={(e) => setTavily(e.target.value)}
          autoComplete="off"
        />
        <SettingsField
          title="Exa API Key"
          type={type}
          value={exa}
          onChange={(e) => setExa(e.target.value)}
          autoComplete="off"
        />
        <SettingsField
          title="SearXNG URL"
          type="text"
          value={searxng}
          onChange={(e) => setSearxng(e.target.value)}
          placeholder="https://searxng.example"
        />
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Button type="button" variant="outline" size="sm" onClick={() => setShow((v) => !v)}>
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            {show ? "隐藏" : "显示"}
          </Button>
          <Button type="button" onClick={save}>
            保存检索配置
          </Button>
        </div>
        {status ? <p className="form-hint">{status}</p> : null}
      </div>
    </div>
  );
}
