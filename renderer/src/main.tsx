import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";

import App from "./App";
import { initAppearance } from "./lib/appearance";
import "./styles/ds-tokens.css";
import "./styles/app.css";
import "./styles/markdown.css";

initAppearance();

// Demo chrome (floating shell + fake traffic lights) is for browser preview only.
// Real Electron already has a native window — fill it and hide the mock chrome.
if (typeof navigator !== "undefined" && /Electron/i.test(navigator.userAgent)) {
  document.documentElement.classList.add("electron");
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
