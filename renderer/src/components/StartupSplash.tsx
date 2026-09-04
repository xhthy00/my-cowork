import { useEffect, useState } from "react";

import cowBlink from "@/assets/brand/cow-blink.webp";
import logoHorizontal from "@/assets/brand/logo-horizontal.png";

type BootStatus = "loading" | "failed";

/**
 * Full-screen splash shown until the Python backend is ready.
 * Uses a cropped transparent WebP of the blinking cow icon (no letterbox).
 */
export default function StartupSplash() {
  const [status, setStatus] = useState<BootStatus>("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void window.api.getBackendUrl().then((url) => {
      if (url) setStatus("loading");
    });
    const offReady = window.api.onBackendReady?.(() => setStatus("loading")) ?? (() => {});
    const offFailed =
      window.api.onBackendFailed?.((msg) => {
        setStatus("failed");
        setMessage(msg);
      }) ?? (() => {});
    return () => {
      offReady();
      offFailed();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-gradient-to-b from-[#fafbff] via-[#f4f5fb] to-[#eef0f8] [color-scheme:light]">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-1/2 h-[520px] w-[520px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(139,92,246,0.14),transparent_70%)]" />
      </div>

      <div className="relative flex flex-col items-center gap-6">
        <img
          src={cowBlink}
          alt=""
          className="select-none [animation:icon-in_0.7s_cubic-bezier(0.22,1,0.36,1)_both]"
          style={{
            width: "clamp(180px, 22vw, 240px)",
            height: "auto",
            filter: "drop-shadow(0 18px 36px rgba(124, 58, 237, 0.28))",
          }}
          draggable={false}
        />
        {status === "failed" && (
          <div className="absolute top-0 flex h-[240px] w-[240px] items-center justify-center rounded-[28%] bg-black/40 text-4xl text-red-300">
            !
          </div>
        )}

        <img
          src={logoHorizontal}
          alt="MyCowork"
          className="h-16 w-auto max-w-[min(420px,78vw)] select-none opacity-0 [animation:logo-in_0.9s_0.15s_cubic-bezier(0.22,1,0.36,1)_forwards,logo-float_3s_1.1s_ease-in-out_infinite]"
          style={{ filter: "drop-shadow(0 8px 18px rgba(30, 41, 90, 0.12))" }}
          draggable={false}
        />

        <div className="flex flex-col items-center gap-3">
          {status === "loading" && (
            <div className="h-1 w-52 overflow-hidden rounded-full bg-[#e4e5ee]">
              <div className="h-full w-1/3 rounded-full bg-gradient-to-r from-violet-500 via-purple-400 to-orange-400 [animation:shimmer_1.5s_ease-in-out_infinite]" />
            </div>
          )}
          <div className="text-center">
            {status === "loading" ? (
              <>
                <div className="text-sm text-[#3f3e3d] [animation:fade-in_0.5s_0.35s_ease-out_both]">
                  正在启动，请稍候
                </div>
                <div className="mt-1 text-xs text-[#6b6a69] [animation:fade-in_0.5s_0.45s_ease-out_both]">
                  正在加载本地引擎
                </div>
              </>
            ) : (
              <>
                <div className="text-base font-medium text-red-600">后端启动失败</div>
                <div className="mt-2 max-w-md break-words text-xs text-[#535352]">
                  {message || "未知错误"}
                </div>
                <button
                  type="button"
                  className="mt-3 rounded-lg bg-gradient-to-r from-violet-500 to-orange-400 px-4 py-1.5 text-xs text-white shadow-md transition-transform hover:scale-105"
                  onClick={() => window.api.restartBackend().catch(() => {})}
                >
                  重试
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(300%); }
        }
        @keyframes icon-in {
          0% { opacity: 0; transform: scale(0.86); }
          100% { opacity: 1; transform: scale(1); }
        }
        @keyframes logo-in {
          0% { opacity: 0; transform: translateY(16px) scale(0.95); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes logo-float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
        @keyframes fade-in {
          0% { opacity: 0; }
          100% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
