import { getModelCatalog } from "./model_catalog";
import { runtimeCapability } from "./model_capabilities";
import {
  loadModels,
  toBackendProvider,
  upsertConnection,
  validateConnection,
  type ModelConnection,
} from "./models_store";
import { deleteKey, getKey, setKey } from "./keychain";

/** Validate before touching credentials; undo a key change if persistence fails. */
export async function saveModelConnection(
  input: ModelConnection & { apiKey?: string },
) {
  const { apiKey, ...connection } = input;
  validateConnection(connection);
  const current = loadModels();
  const catalog = getModelCatalog();
  for (const profile of current.profiles.filter(
    (p) => p.connectionId === connection.id,
  )) {
    runtimeCapability(
      {
        ...profile,
        provider: connection.provider,
        baseUrl: connection.baseUrl,
      },
      catalog,
    );
  }
  const account =
    current.connections?.find((c) => c.id === connection.id)?.keyAccount ??
    `connection:${connection.id}`;
  const key = apiKey?.trim();
  const previousKey = key ? await getKey("my-cowork", account) : null;
  if (key) await setKey("my-cowork", account, key);
  try {
    return upsertConnection(connection);
  } catch (error) {
    if (key) {
      if (previousKey !== null) await setKey("my-cowork", account, previousKey);
      else await deleteKey("my-cowork", account);
    }
    throw error;
  }
}

/** Called only in the main process. Never exposed through preload or trace events. */
export async function runtimeModelsPayload() {
  const state = loadModels();
  const catalog = getModelCatalog();
  const models = await Promise.all(
    state.profiles.map(async (profile) => {
      const connection = state.connections?.find(
        (c) => c.id === profile.connectionId,
      );
      const key = await getKey(
        "my-cowork",
        connection?.keyAccount ?? `model:${profile.id}`,
      );
      return {
        id: profile.id,
        provider: toBackendProvider(profile.provider),
        model: profile.model,
        base_url: profile.baseUrl,
        api_key: key || "",
        ...runtimeCapability(profile, catalog),
        compaction_ratio: state.compactionRatio ?? 0.8,
      };
    }),
  );
  return { models, active_id: state.activeId };
}
