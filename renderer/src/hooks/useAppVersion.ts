import { useEffect, useState } from "react";
import { version as packageVersion } from "../../../package.json";

export function useAppVersion() {
  const [version, setVersion] = useState(packageVersion);
  useEffect(() => {
    let disposed = false;
    void window.api?.getUpdaterStatus?.().then(status => {
      if (!disposed && status?.currentVersion) setVersion(status.currentVersion.replace(/^v/, ""));
    }).catch(() => undefined);
    return () => { disposed = true; };
  }, []);
  return version;
}
