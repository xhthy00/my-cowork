import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("electron", () => ({
  safeStorage: {
    isEncryptionAvailable: () => true,
    getSelectedStorageBackend: () => "keychain",
    encryptString: (value: string) => Buffer.from(`encrypted:${value}`),
    decryptString: (value: Buffer) => {
      const contents = value.toString();
      if (!contents.startsWith("encrypted:")) throw new Error("invalid ciphertext");
      return contents.slice("encrypted:".length);
    },
  },
}));

import {
  buildPythonEnv,
  deleteKey,
  getKey,
  initKeychain,
  overrideBackend,
  setKey,
} from "../electron/keychain";
import { initModelsStore, upsertProfile } from "../electron/models_store";

describe("keychain", () => {
  it("scopes every native-store account and restores the ordinary service", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mcapp-scope-"));
    const get = vi.fn().mockResolvedValue(null), set = vi.fn(), remove = vi.fn().mockResolvedValue(true);
    const scope = 'a'.repeat(64);
    initKeychain(dir, scope);
    overrideBackend({ get, set, delete: remove });
    try {
      for (const account of ['model:x', 'openai', 'lark:app_secret', 'search:brave']) {
        await getKey('my-cowork', account); await setKey('my-cowork', account, 'sentinel'); await deleteKey('my-cowork', account);
        expect(get).toHaveBeenCalledWith(`my-cowork:app-dev:${scope}`, account);
        expect(set).toHaveBeenCalledWith(`my-cowork:app-dev:${scope}`, account, 'sentinel');
        expect(remove).toHaveBeenCalledWith(`my-cowork:app-dev:${scope}`, account);
      }
      initKeychain(dir); overrideBackend({ get, set });
      await getKey('my-cowork', 'openai');
      expect(get).toHaveBeenLastCalledWith('my-cowork', 'openai');
    } finally { initKeychain(dir); fs.rmSync(dir, { recursive: true, force: true }); }
  });
  it("getKey returns value from backend", async () => {
    overrideBackend({
      get: vi.fn().mockResolvedValue("sk-test-key"),
      set: vi.fn(),
    });

    const result = await getKey("my-cowork", "openai");
    expect(result).toBe("sk-test-key");
  });

  it("getKey returns null when backend returns null", async () => {
    overrideBackend({
      get: vi.fn().mockResolvedValue(null),
      set: vi.fn(),
    });

    const result = await getKey("my-cowork", "openai");
    expect(result).toBeNull();
  });

  it("setKey calls backend with correct args", async () => {
    const setter = vi.fn().mockResolvedValue(undefined);
    overrideBackend({ get: vi.fn(), set: setter });

    await setKey("my-cowork", "openai", "sk-new-key");
    expect(setter).toHaveBeenCalledWith("my-cowork", "openai", "sk-new-key");
  });

  it("stores credentials encrypted and persists across reads", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-key-"));
    initKeychain(dir);
    await setKey("my-cowork", "openai", "sk-persisted");
    expect(fs.existsSync(path.join(dir, "credentials.enc"))).toBe(true);
    expect(fs.existsSync(path.join(dir, "credentials.json"))).toBe(false);
    expect(await getKey("my-cowork", "openai")).toBe("sk-persisted");
    initKeychain(dir);
    expect(await getKey("my-cowork", "openai")).toBe("sk-persisted");
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("reads a key saved by the newer encrypted credential store", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-key-newer-"));
    const encrypted = Buffer.from('encrypted:{"my-cowork:model:active":"sk-restored"}');
    fs.writeFileSync(path.join(dir, "credentials.enc"), encrypted);
    initKeychain(dir);
    expect(await getKey("my-cowork", "model:active")).toBe("sk-restored");
    expect(fs.readFileSync(path.join(dir, "credentials.enc"))).toEqual(encrypted);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("deleteKey removes a stored secret", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-key-del-"));
    initKeychain(dir);
    await setKey("my-cowork", "model:x", "sk-gone");
    expect(await deleteKey("my-cowork", "model:x")).toBe(true);
    expect(await getKey("my-cowork", "model:x")).toBeNull();
    fs.rmSync(dir, { recursive: true, force: true });
  });
});

describe("buildPythonEnv", () => {
  let tmp: string;

  beforeEach(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-env-"));
    initModelsStore(tmp);
  });

  it("includes api key when keychain returns a value", async () => {
    overrideBackend({
      get: vi.fn().mockResolvedValue("sk-from-keychain"),
      set: vi.fn(),
    });

    const env = await buildPythonEnv();
    expect(env.MY_COWORK_API_KEY).toBe("sk-from-keychain");
  });

  it("does not set api key when keychain returns null", async () => {
    overrideBackend({
      get: vi.fn().mockResolvedValue(null),
      set: vi.fn(),
    });

    const env = await buildPythonEnv();
    expect(env.MY_COWORK_API_KEY).toBeUndefined();
  });

  it("includes active model provider/model/key", async () => {
    initKeychain(tmp);
    upsertProfile({
      id: "m1",
      name: "Claude",
      provider: "anthropic",
      model: "claude-sonnet-4-20250514",
    });
    await setKey("my-cowork", "model:m1", "sk-active");

    const env = await buildPythonEnv();
    expect(env.MY_COWORK_API_KEY).toBe("sk-active");
    expect(env.MY_COWORK_PROVIDER).toBe("anthropic");
    expect(env.MY_COWORK_MODEL).toBe("claude-sonnet-4-20250514");
  });

  it("maps openrouter UX provider to openai_compat env", async () => {
    initKeychain(tmp);
    upsertProfile({
      id: "or1",
      name: "OpenRouter",
      provider: "openrouter",
      model: "openai/gpt-4o-mini",
      baseUrl: "https://openrouter.ai/api/v1",
      category: "cloud_byok",
      presetId: "openrouter",
    });
    await setKey("my-cowork", "model:or1", "sk-or");

    const env = await buildPythonEnv();
    expect(env.MY_COWORK_PROVIDER).toBe("openai_compat");
    expect(env.MY_COWORK_BASE_URL).toBe("https://openrouter.ai/api/v1");
    expect(env.MY_COWORK_API_KEY).toBe("sk-or");
  });

  it("injects Lark credentials from keychain", async () => {
    initKeychain(tmp);
    await setKey("my-cowork", "lark:app_id", "cli_test");
    await setKey("my-cowork", "lark:app_secret", "sec_test");
    await setKey("my-cowork", "lark:verify_token", "tok_test");
    await setKey("my-cowork", "lark:encrypt_key", "enc_test");

    const env = await buildPythonEnv();
    expect(env.LARK_APP_ID).toBe("cli_test");
    expect(env.LARK_APP_SECRET).toBe("sec_test");
    expect(env.LARK_VERIFY_TOKEN).toBe("tok_test");
    expect(env.LARK_ENCRYPT_KEY).toBe("enc_test");
  });

  it("injects search credentials from keychain", async () => {
    initKeychain(tmp);
    await setKey("my-cowork", "search:provider", "bocha");
    await setKey("my-cowork", "search:bocha", "bocha-key");
    await setKey("my-cowork", "search:brave", "brave-key");

    const env = await buildPythonEnv();
    expect(env.MY_COWORK_SEARCH_PROVIDER).toBe("bocha");
    expect(env.BOCHA_API_KEY).toBe("bocha-key");
    expect(env.BRAVE_API_KEY).toBe("brave-key");
  });

  it("injects IMA credentials from keychain", async () => {
    initKeychain(tmp);
    await setKey("my-cowork", "ima:client_id", "ima-cid");
    await setKey("my-cowork", "ima:api_key", "ima-secret");

    const env = await buildPythonEnv();
    expect(env.IMA_OPENAPI_CLIENTID).toBe("ima-cid");
    expect(env.IMA_OPENAPI_APIKEY).toBe("ima-secret");
  });
});
