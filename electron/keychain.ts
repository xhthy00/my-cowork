/**
 * Keychain service wrapping the OS-native credential store.
 *
 * Prefers ``keytar`` when available. Otherwise falls back to a JSON file under
 * the app userData directory (configured via ``initKeychain``). An in-memory
 * Map is used only until ``initKeychain`` runs (and in unit tests).
 */

import * as fs from "fs";
import * as path from "path";

import { getActiveProfile, toBackendProvider } from "./models_store";

const SERVICE = "my-cowork";

// ── back-end ─────────────────────────────────────────────────────────────────
interface KeychainBackend {
  get(service: string, account: string): Promise<string | null>;
  set(service: string, account: string, password: string): Promise<void>;
  delete?(service: string, account: string): Promise<boolean>;
}

class MemoryBackend implements KeychainBackend {
  private _store = new Map<string, string>();

  async get(service: string, account: string): Promise<string | null> {
    return this._store.get(`${service}:${account}`) ?? null;
  }

  async set(service: string, account: string, password: string): Promise<void> {
    this._store.set(`${service}:${account}`, password);
  }

  async delete(service: string, account: string): Promise<boolean> {
    return this._store.delete(`${service}:${account}`);
  }
}

class FileBackend implements KeychainBackend {
  constructor(private readonly filePath: string) {}

  private readAll(): Record<string, string> {
    try {
      return JSON.parse(fs.readFileSync(this.filePath, "utf8")) as Record<string, string>;
    } catch {
      return {};
    }
  }

  private writeAll(data: Record<string, string>): void {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
    fs.writeFileSync(this.filePath, JSON.stringify(data), { mode: 0o600 });
  }

  async get(service: string, account: string): Promise<string | null> {
    return this.readAll()[`${service}:${account}`] ?? null;
  }

  async set(service: string, account: string, password: string): Promise<void> {
    const data = this.readAll();
    data[`${service}:${account}`] = password;
    this.writeAll(data);
  }

  async delete(service: string, account: string): Promise<boolean> {
    const data = this.readAll();
    const key = `${service}:${account}`;
    if (!(key in data)) return false;
    delete data[key];
    this.writeAll(data);
    return true;
  }
}

let _backend: KeychainBackend = new MemoryBackend();

function tryKeytar(): KeychainBackend | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const kt = require("keytar") as {
      getPassword: (s: string, a: string) => Promise<string | null>;
      setPassword: (s: string, a: string, p: string) => Promise<void>;
      deletePassword: (s: string, a: string) => Promise<boolean>;
    };
    return {
      get: (s, a) => kt.getPassword(s, a),
      set: (s, a, p) => kt.setPassword(s, a, p),
      delete: (s, a) => kt.deletePassword(s, a),
    };
  } catch {
    return null;
  }
}

/** Call once from Electron main after ``app.ready``. Prefers keytar, else file. */
export function initKeychain(userDataPath: string): void {
  const keytar = tryKeytar();
  if (keytar) {
    _backend = keytar;
    return;
  }
  _backend = new FileBackend(path.join(userDataPath, "credentials.json"));
}

// ── public API ──────────────────────────────────────────────────────────────

export function overrideBackend(backend: KeychainBackend): void {
  _backend = backend;
}

export async function getKey(service: string, account: string): Promise<string | null> {
  return _backend.get(service, account);
}

export async function setKey(service: string, account: string, password: string): Promise<void> {
  return _backend.set(service, account, password);
}

export async function deleteKey(service: string, account: string): Promise<boolean> {
  if (_backend.delete) {
    return _backend.delete(service, account);
  }
  // Fallback: overwrite with empty then ignore (legacy backends).
  await _backend.set(service, account, "");
  return true;
}

export const LARK_APP_ID_ACCOUNT = "lark:app_id";
export const LARK_APP_SECRET_ACCOUNT = "lark:app_secret";
export const LARK_VERIFY_TOKEN_ACCOUNT = "lark:verify_token";
export const LARK_ENCRYPT_KEY_ACCOUNT = "lark:encrypt_key";

async function injectLarkEnv(env: Record<string, string>): Promise<void> {
  const appId = (await getKey(SERVICE, LARK_APP_ID_ACCOUNT))?.trim();
  const appSecret = (await getKey(SERVICE, LARK_APP_SECRET_ACCOUNT))?.trim();
  const verifyToken = (await getKey(SERVICE, LARK_VERIFY_TOKEN_ACCOUNT))?.trim();
  const encryptKey = (await getKey(SERVICE, LARK_ENCRYPT_KEY_ACCOUNT))?.trim();
  if (appId) env.LARK_APP_ID = appId;
  if (appSecret) env.LARK_APP_SECRET = appSecret;
  if (verifyToken) env.LARK_VERIFY_TOKEN = verifyToken;
  if (encryptKey) env.LARK_ENCRYPT_KEY = encryptKey;
}

export async function buildPythonEnv(): Promise<Record<string, string>> {
  const env: Record<string, string> = {};
  const active = getActiveProfile();
  if (active) {
    const key =
      (await getKey(SERVICE, `model:${active.id}`)) ??
      (await getKey(SERVICE, "openai"));
    if (key) {
      env["MY_COWORK_API_KEY"] = key;
    }
    env["MY_COWORK_PROVIDER"] = toBackendProvider(active.provider);
    env["MY_COWORK_MODEL"] = active.model;
    if (active.baseUrl) {
      env["MY_COWORK_BASE_URL"] = active.baseUrl;
    }
    await injectLarkEnv(env);
    return env;
  }

  const legacy = await getKey(SERVICE, "openai");
  if (legacy) {
    env["MY_COWORK_API_KEY"] = legacy;
  }
  await injectLarkEnv(env);
  return env;
}
