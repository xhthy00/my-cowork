import { runtimeCapability } from "./model_capabilities";
import { loadModels } from "./models_store";
import * as fs from "fs";
import * as path from "path";
import bundled from "./model-catalog.json";
import type {
  ModelCatalog,
  ModelCapability,
  ReasoningOption,
} from "./model_capabilities";

let cachePath = "";
function validCatalog(value: ModelCatalog): boolean {
  const positive = (n: unknown) =>
    typeof n === "number" && Number.isInteger(n) && n > 0;
  return Boolean(
    value &&
      typeof value.updatedAt === "string" &&
      Array.isArray(value.models) &&
      value.models.length >= 100 &&
      value.models.every(
        (m) =>
          m &&
          [m.id, m.provider, m.model, m.name].every(
            (v) => typeof v === "string" && v.length > 0,
          ) &&
          positive(m.context) &&
          positive(m.output) &&
          (m.input == null || positive(m.input)) &&
          (m.reasoning === undefined || typeof m.reasoning === "boolean") &&
          Array.isArray(m.options) &&
          m.options.every(
            (o) =>
              o &&
              (o.type === "toggle" ||
                (o.type === "effort" &&
                  Array.isArray(o.values) &&
                  o.values.length > 0 &&
                  o.values.every(
                    (v) => typeof v === "string" && v.length > 0,
                  )) ||
                (o.type === "budget_tokens" &&
                  (o.min == null || Number.isInteger(o.min)) &&
                  (o.max == null || positive(o.max)) &&
                  (o.min == null || o.max == null || o.min <= o.max))),
          ),
      ),
  );
}
export function initModelCatalog(userData: string) {
  cachePath = path.join(userData, "model-catalog.json");
}
export function getModelCatalog(): ModelCatalog {
  if (cachePath && fs.existsSync(cachePath)) {
    try {
      const value = JSON.parse(fs.readFileSync(cachePath, "utf8"));
      if (validCatalog(value)) return value;
    } catch {
      /* use bundled offline snapshot */
    }
  }
  return bundled as ModelCatalog;
}
export async function refreshModelCatalog(): Promise<ModelCatalog> {
  const response = await fetch("https://models.dev/api.json", {
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error("能力目录更新失败，仍使用现有目录");
  const data = (await response.json()) as Record<
    string,
    { models?: Record<string, Record<string, unknown>> }
  >;
  const models: ModelCapability[] = [];
  for (const [provider, source] of Object.entries(data))
    for (const [model, m] of Object.entries(source.models ?? {})) {
      const limit = m.limit as
        | { context?: number; input?: number; output?: number }
        | undefined;
      const modalities = m.modalities as { output?: string[] } | undefined;
      if (m.tool_call !== true || !modalities?.output?.includes("text"))
        continue;
      if (
        !limit ||
        !Number.isFinite(limit.context) ||
        (limit.context ?? 0) < 4096 ||
        !Number.isFinite(limit.output) ||
        (limit.output ?? 0) <= 0
      )
        continue;
      const options = Array.isArray(m.reasoning_options)
        ? m.reasoning_options.filter(
            (o): o is ReasoningOption =>
              o &&
              typeof o === "object" &&
              ["toggle", "effort", "budget_tokens"].includes(o.type),
          )
        : [];
      models.push({
        id: `${provider}/${model}`,
        provider,
        model,
        name: typeof m.name === "string" ? m.name : model,
        reasoning: typeof m.reasoning === "boolean" ? m.reasoning : undefined,
        options,
        context: limit.context!,
        input: limit.input,
        output: limit.output,
      });
    }
  if (models.length < 100)
    throw new Error("能力目录数据不完整，仍使用现有目录");
  const catalog = { updatedAt: new Date().toISOString(), models };
  if (!validCatalog(catalog))
    throw new Error("能力目录数据无效，仍使用现有目录");
  for (const profile of loadModels().profiles)
    runtimeCapability(profile, catalog);
  if (cachePath) {
    fs.writeFileSync(`${cachePath}.tmp`, JSON.stringify(catalog));
    fs.renameSync(`${cachePath}.tmp`, cachePath);
  }
  return catalog;
}
