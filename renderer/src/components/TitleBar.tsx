import aisIcon from "@/assets/brand/ais-app-icon.png";

const isElectron =
  typeof navigator !== "undefined" && /Electron/i.test(navigator.userAgent);

export default function TitleBar() {
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
    </div>
  );
}
