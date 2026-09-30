import type { ModelProfile } from "./models_store";

export interface ReasoningOption {
  type: "toggle" | "effort" | "budget_tokens";
  values?: string[] | null;
  min?: number;
  max?: number;
}
export interface ModelCapability {
  id: string;
  provider: string;
  model: string;
  name: string;
  reasoning?: boolean;
  options: ReasoningOption[];
  context: number;
  input?: number | null;
  output?: number | null;
}
export interface ModelCatalog {
  updatedAt: string;
  models: ModelCapability[];
}

const HOSTS: Record<string, string> = {
  "api.openai.com": "openai",
  "api.anthropic.com": "anthropic",
  "openrouter.ai": "openrouter",
  "api.deepseek.com": "deepseek",
  "dashscope.aliyuncs.com": "alibaba-cn",
  "dashscope-intl.aliyuncs.com": "alibaba",
  "api.moonshot.cn": "moonshotai-cn",
  "api.moonshot.ai": "moonshotai",
  "api.minimax.io": "minimax",
  "api.minimaxi.com": "minimax",
  "open.bigmodel.cn": "zhipuai",
  "api.z.ai": "zai",
  "generativelanguage.googleapis.com": "google",
};
export function capabilityFor(
  profile: Pick<
    ModelProfile,
    "model" | "baseUrl" | "provider" | "capabilityId"
  >,
  catalog: ModelCatalog,
) {
  if (profile.capabilityId)
    return catalog.models.find((m) => m.id === profile.capabilityId);
  let provider: string | undefined;
  try {
    provider =
      HOSTS[
        new URL(
          profile.baseUrl ||
            (profile.provider === "anthropic"
              ? "https://api.anthropic.com"
              : "https://api.openai.com"),
        ).hostname
      ];
  } catch {
    /* manual association remains available */
  }
  return catalog.models.find(
    (m) => m.provider === provider && m.model === profile.model,
  );
}

export function reasoningAdapter(
  profile: ModelProfile,
  capability?: ModelCapability,
): string {
  if (profile.reasoningAdapter) return profile.reasoningAdapter;
  if (profile.provider === "anthropic") return "anthropic";
  let host = "";
  try {
    host = new URL(profile.baseUrl || "https://api.openai.com").hostname;
  } catch {
    return "default";
  }
  const provider = HOSTS[host];
  if (provider === "openrouter") return "openrouter";
  if (provider === "openai")
    return capability?.reasoning ? "openai-responses" : "openai";
  if (provider === "google") return "google";
  if (provider === "minimax") return "minimax";
  if (provider === "deepseek") return "deepseek";
  if (provider?.startsWith("moonshotai")) return "moonshot";
  if (provider?.startsWith("alibaba")) return "qwen";
  if (provider === "zai" || provider === "zhipuai") return "thinking";
  // Metadata describes model abilities, not the wire protocol of an unknown proxy.
  return "default";
}

export const EFFORT_LABELS: Record<string, string> = {
  none: "关闭",
  minimal: "最低",
  low: "低",
  medium: "中",
  high: "高",
  xhigh: "极高",
  max: "最高",
  default: "默认",
};

export function runtimeCapability(
  profile: ModelProfile,
  catalog: ModelCatalog,
) {
  const cap = capabilityFor(profile, catalog);
  if (profile.capabilityId && !cap) throw new Error("关联的能力目录 ID 不存在");
  const selection = profile.reasoning ?? {};
  const options = cap?.options ?? [];
  if (
    selection.effort &&
    !options.some(
      (o) => o.type === "effort" && o.values?.includes(selection.effort!),
    )
  )
    throw new Error("此模型不支持所选思考强度，请重新选择");
  if (
    selection.enabled !== undefined &&
    !options.some((o) => o.type === "toggle")
  )
    throw new Error("此模型不支持切换思考模式");
  const budget = options.find((o) => o.type === "budget_tokens");
  if (
    selection.budgetTokens !== undefined &&
    (!budget ||
      !Number.isInteger(selection.budgetTokens) ||
      selection.budgetTokens < Math.max(0, budget.min ?? 0) ||
      selection.budgetTokens > (budget.max ?? cap?.output ?? 131072))
  )
    throw new Error("思考预算超出模型支持范围");
  const mode = reasoningAdapter(profile, cap);
  const supported = [
    "default",
    "openai",
    "openai-responses",
    "anthropic",
    "deepseek",
    "moonshot",
    "qwen",
    "openrouter",
    "thinking",
    "minimax",
    "google",
  ];
  if (!supported.includes(mode)) throw new Error("思考参数协议无效");
  if ((profile.provider === "anthropic") !== (mode === "anthropic"))
    throw new Error("思考参数协议与连接协议不匹配");
  if (
    selection.budgetTokens !== undefined &&
    !["anthropic", "qwen", "google", "openrouter"].includes(mode)
  )
    throw new Error("此参数协议不支持预算参数");
  if (
    selection.enabled !== undefined &&
    ["openai", "openai-responses"].includes(mode)
  )
    throw new Error("此参数协议不支持思考开关");
  if (
    selection.enabled === false &&
    ((selection.effort !== undefined && mode !== "anthropic") || selection.budgetTokens !== undefined)
  )
    throw new Error("关闭思考时不能同时指定强度或预算");
  if (
    ["google", "openrouter"].includes(mode) &&
    selection.effort !== undefined &&
    selection.budgetTokens !== undefined
  )
    throw new Error("此服务的思考强度和预算不能同时指定");
  if (
    mode === "default" &&
    Object.values(selection).some((v) => v !== undefined)
  )
    throw new Error("请先选择服务支持的思考参数协议");
  const context = profile.contextWindow ?? cap?.context ?? 200000;
  if (!Number.isInteger(context) || context < 4096 || context > 10000000)
    throw new Error("上下文窗口须为 4096 到 10000000 tokens");
  // Reserve a bounded generation budget instead of reserving the model's entire maximum.
  const output = Math.min(cap?.output || 32768, 32768, Math.floor(context / 4));
  if (selection.budgetTokens !== undefined && selection.budgetTokens >= output)
    throw new Error(`思考预算须小于本次输出预算 ${output}`);
  return {
    context_window: context,
    input_limit: cap?.input || null,
    output_limit: output,
    reasoning_mode: mode,
    reasoning_effort: selection.effort,
    thinking_enabled: selection.enabled,
    thinking_budget: selection.budgetTokens,
    allowed_efforts: options.find((o) => o.type === "effort")?.values ?? [],
    allow_thinking_toggle: options.some((o) => o.type === "toggle"),
    budget_min: budget ? Math.max(0, budget.min ?? 0) : null,
    budget_max: budget?.max ?? null,
  };
}
