import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { beforeEach, describe, expect, it, vi } from "vitest";

const secureStorage = vi.hoisted(() => ({
  isEncryptionAvailable: vi.fn(() => true),
  getSelectedStorageBackend: vi.fn(() => "gnome_libsecret"),
  encryptString: vi.fn((text: string) => Buffer.from(`encrypted:${Buffer.from(text).toString("base64")}`)),
  decryptString: vi.fn((data: Buffer) => Buffer.from(data.toString().slice(10), "base64").toString()),
}));
vi.mock("electron", () => ({ safeStorage: secureStorage }));
beforeEach(() => { secureStorage.isEncryptionAvailable.mockReturnValue(true); });

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

  it("encrypted credentials persist without writing plaintext", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-key-"));
    initKeychain(dir);
    await setKey("my-cowork", "openai", "sk-persisted");
    expect(await getKey("my-cowork", "openai")).toBe("sk-persisted");
    expect(fs.existsSync(path.join(dir, "credentials.json"))).toBe(false);
    expect(fs.readFileSync(path.join(dir, "credentials.enc"), "utf8")).not.toContain("sk-persisted");
    initKeychain(dir);
    expect(await getKey("my-cowork", "openai")).toBe("sk-persisted");
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("refuses new secrets when OS encryption is unavailable", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-key-unavailable-"));
    initKeychain(dir);
    secureStorage.isEncryptionAvailable.mockReturnValue(false);
    await expect(setKey("my-cowork", "openai", "fake-secret")).rejects.toThrow();
    expect(fs.readdirSync(dir)).toEqual([]);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("migrates old plaintext only after encrypted data can be read back", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-key-migrate-"));
    const legacy = path.join(dir, "credentials.json");
    fs.writeFileSync(legacy, JSON.stringify({ "my-cowork:openai": "fake-legacy" }));
    initKeychain(dir);
    secureStorage.isEncryptionAvailable.mockReturnValue(false);
    await expect(getKey("my-cowork", "openai")).rejects.toThrow();
    expect(fs.existsSync(legacy)).toBe(true);
    secureStorage.isEncryptionAvailable.mockReturnValue(true);
    expect(await getKey("my-cowork", "openai")).toBe("fake-legacy");
    expect(fs.existsSync(legacy)).toBe(false);
    initKeychain(dir);
    expect(await getKey("my-cowork", "openai")).toBe("fake-legacy");
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

  it("keeps the legacy file when encryption verification fails", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-key-verify-"));
    const legacy = path.join(dir, "credentials.json");
    fs.writeFileSync(legacy, JSON.stringify({ "my-cowork:openai": "fake-legacy" }));
    initKeychain(dir);
    secureStorage.decryptString.mockReturnValueOnce("wrong");
    await expect(getKey("my-cowork", "openai")).rejects.toThrow();
    expect(fs.existsSync(legacy)).toBe(true);
    expect(fs.existsSync(path.join(dir, "credentials.enc"))).toBe(false);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("does not replace an unreadable encrypted file on a new save", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-key-corrupt-"));
    const encrypted = path.join(dir, "credentials.enc");
    fs.writeFileSync(encrypted, "corrupt ciphertext");
    initKeychain(dir);
    await expect(setKey("my-cowork", "openai", "new-secret")).rejects.toThrow();
    expect(fs.readFileSync(encrypted, "utf8")).toBe("corrupt ciphertext");
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
