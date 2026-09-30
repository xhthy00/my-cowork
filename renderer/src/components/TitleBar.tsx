import { navigateToModelsConfig, useModels } from "../hooks/useModels";
import aisIcon from "@/assets/brand/ais-app-icon.png";

const isElectron =
  typeof navigator !== "undefined" && /Electron/i.test(navigator.userAgent);

export default function TitleBar() {
  const { models, active, setActive, switching, status } = useModels();

  async function onSelectModel(id: string) {
    if (!id || id === models.activeId) return;
    await setActive(id);
  }

  const label = active?.name ?? "未配置模型";

  return (
    <div className={`titlebar ${isElectron ? "titlebar-electron" : ""}`}>
      {!isElectron && (
        <div className="traffic" aria-hidden="true">
          <span className="r" />
          <span className="y" />
          <span className="g" />
        </div>
      )}
      <div className="titlebar-brand">
        <img className="logo" src={aisIcon} alt="" width={22} height={22} />
        MyCowork
      </div>
      <div className="titlebar-spacer" />
      <div className="titlebar-actions">
        {isElectron && models.profiles.length > 0 ? (
          <label
            className="pill select model-switch"
            title={switching ? "正在切换模型…" : status || "切换模型"}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2a4 4 0 0 1 4 4v2H8V6a4 4 0 0 1 4-4z" />
              <rect x="4" y="10" width="16" height="10" rx="2" />
              <circle cx="9" cy="15" r="1" />
              <circle cx="15" cy="15" r="1" />
            </svg>
            <select
              aria-label="切换模型"
              value={models.activeId ?? ""}
              disabled={switching}
              onChange={(e) => void onSelectModel(e.target.value)}
            >
              {models.profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <button
            className="pill select"
            type="button"
            title="去配置模型"
            onClick={navigateToModelsConfig}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2a4 4 0 0 1 4 4v2H8V6a4 4 0 0 1 4-4z" />
              <rect x="4" y="10" width="16" height="10" rx="2" />
              <circle cx="9" cy="15" r="1" />
              <circle cx="15" cy="15" r="1" />
            </svg>
            {label}
          </button>
        )}
      </div>
    </div>
  );
}
