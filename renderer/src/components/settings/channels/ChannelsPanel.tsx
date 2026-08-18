import { useCallback, useEffect, useState } from "react";

import { channelApi } from "@/lib/channelApi";
import type { ChannelPluginStatus } from "@/types/channel";

import ChannelItem from "./ChannelItem";
import LarkConfigForm from "./LarkConfigForm";
import WeixinConfigForm from "./WeixinConfigForm";

const ORDER = ["telegram", "lark", "dingtalk", "weixin"] as const;

const META: Record<
  (typeof ORDER)[number],
  { title: string; description: string; accent: string; initial: string }
> = {
  telegram: {
    title: "Telegram",
    description: "通过 Telegram 与办公助手对话",
    accent: "bg-[#229ED9]",
    initial: "Tg",
  },
  lark: {
    title: "飞书",
    description: "通过飞书机器人与办公助手对话（长连接，无需公网 URL）",
    accent: "bg-[#3370FF]",
    initial: "飞",
  },
  dingtalk: {
    title: "钉钉",
    description: "通过钉钉与办公助手对话",
    accent: "bg-[#1677FF]",
    initial: "钉",
  },
  weixin: {
    title: "微信",
    description: "通过微信 ClawBot 与办公助手对话（扫码登录，无需公网 URL）",
    accent: "bg-[#07C160]",
    initial: "微",
  },
};

export default function ChannelsPanel() {
  const [plugins, setPlugins] = useState<ChannelPluginStatus[]>([]);
  const [toast, setToast] = useState("");
  const [larkStatus, setLarkStatus] = useState<ChannelPluginStatus | null>(null);
  const [weixinStatus, setWeixinStatus] = useState<ChannelPluginStatus | null>(null);

  const loadPlugins = useCallback(async () => {
    try {
      const list = await channelApi.getPlugins();
      setPlugins(list);
      setLarkStatus(list.find((p) => p.plugin_id === "lark") ?? null);
      setWeixinStatus(list.find((p) => p.plugin_id === "weixin") ?? null);
    } catch (err) {
      setToast(err instanceof Error ? err.message : "无法加载远程连接");
    }
  }, []);

  useEffect(() => {
    void loadPlugins();
  }, [loadPlugins]);

  useEffect(() => {
    return channelApi.subscribe((ev) => {
      if (ev.type !== "channel.plugin-status-changed") return;
      const status = ev.payload.status as ChannelPluginStatus | undefined;
      if (!status) {
        void loadPlugins();
        return;
      }
      setPlugins((prev) =>
        prev.map((p) => (p.plugin_id === status.plugin_id ? status : p)),
      );
      if (status.plugin_id === "lark") setLarkStatus(status);
      if (status.plugin_id === "weixin") setWeixinStatus(status);
    });
  }, [loadPlugins]);

  async function toggleLark(enabled: boolean) {
    const current = larkStatus ?? plugins.find((p) => p.plugin_id === "lark");
    if (enabled) {
      if (!current?.has_token) {
        setToast("请输入 App ID 和 App Secret");
        return;
      }
      try {
        await channelApi.enablePlugin("lark", {});
        setToast("飞书机器人已启用");
        await loadPlugins();
      } catch (err) {
        setToast(err instanceof Error ? err.message : "启用飞书插件失败");
      }
      return;
    }
    try {
      await channelApi.disablePlugin("lark");
      setToast("飞书机器人已禁用");
      await loadPlugins();
    } catch (err) {
      setToast(err instanceof Error ? err.message : "禁用失败");
    }
  }

  async function toggleWeixin(enabled: boolean) {
    const current = weixinStatus ?? plugins.find((p) => p.plugin_id === "weixin");
    if (enabled) {
      if (!current?.has_token) {
        setToast("请先使用微信扫码登录");
        return;
      }
      try {
        await channelApi.enablePlugin("weixin", {});
        setToast("微信频道已启用");
        await loadPlugins();
      } catch (err) {
        setToast(err instanceof Error ? err.message : "启用微信插件失败");
      }
      return;
    }
    try {
      await channelApi.disablePlugin("weixin");
      setToast("微信频道已禁用");
      await loadPlugins();
    } catch (err) {
      setToast(err instanceof Error ? err.message : "禁用失败");
    }
  }

  const byId = Object.fromEntries(plugins.map((p) => [p.plugin_id, p]));

  return (
    <div>
      <h3>远程连接</h3>
      <p className="panel-desc">
        用飞书、微信等渠道把办公助手当成远程助手。飞书使用官方长连接，微信使用 ClawBot 扫码，无需 Cloudflare 隧道。
      </p>
      {toast ? (
        <p className="form-hint" role="status" data-testid="channel-toast" style={{ marginBottom: 12 }}>
          {toast}
        </p>
      ) : null}
      <div className="flex flex-col gap-3">
        {ORDER.map((id) => {
          const meta = META[id];
          const plugin = byId[id];
          const comingSoon = Boolean(plugin?.coming_soon ?? (id !== "lark" && id !== "weixin"));
          const toggle =
            id === "lark" ? (v: boolean) => void toggleLark(v)
            : id === "weixin" ? (v: boolean) => void toggleWeixin(v)
            : undefined;
          return (
            <ChannelItem
              key={id}
              defaultOpen={id === "lark"}
              channel={{
                id,
                title: meta.title,
                description: meta.description,
                accent: meta.accent,
                initial: meta.initial,
                comingSoon,
                enabled: Boolean(plugin?.enabled) && !comingSoon,
                disabled: comingSoon,
              }}
              onToggleEnabled={toggle}
            >
              {id === "lark" ? (
                <LarkConfigForm
                  pluginStatus={larkStatus}
                  onStatusChange={setLarkStatus}
                  onToast={setToast}
                />
              ) : id === "weixin" ? (
                <WeixinConfigForm
                  pluginStatus={weixinStatus}
                  onStatusChange={setWeixinStatus}
                  onToast={setToast}
                />
              ) : (
                <p className="text-[14px] text-ds-text-neutral-muted-default">
                  {meta.title} 即将推出
                </p>
              )}
            </ChannelItem>
          );
        })}
      </div>
    </div>
  );
}
