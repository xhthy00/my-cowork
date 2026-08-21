import dingtalkLogo from "@/assets/channel/dingtalk.svg";
import larkLogo from "@/assets/channel/lark.svg";
import telegramLogo from "@/assets/channel/telegram.svg";
import weixinLogo from "@/assets/channel/weixin.svg";

const CHANNEL_LOGO_MAP: Record<string, string> = {
  telegram: telegramLogo,
  lark: larkLogo,
  dingtalk: dingtalkLogo,
  weixin: weixinLogo,
};

export function getChannelLogo(id: string): string | undefined {
  return CHANNEL_LOGO_MAP[id];
}
