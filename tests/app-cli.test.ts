import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
const require = createRequire(import.meta.url);
const cli = require('../scripts/mycowork-app.cjs');

describe('plugin developer commands', () => {
  it('replaces inherited app configuration and credentials, preserving OS necessities', () => {
    const env = cli.developmentEnv({ PATH: 'bin', TEMP: 'temp', MY_COWORK_DATA_DIR: 'other', MY_COWORK_API_KEY: 'secret', OPENAI_API_KEY: 'secret', LARK_APP_SECRET: 'secret', ELECTRON_RUN_AS_NODE: '1' }, 'isolated');
    expect(env.PATH).toBe('bin'); expect(env.TEMP).toBe('temp');
    expect(env.MY_COWORK_DATA_DIR).toBe(path.resolve('isolated', 'backend'));
    expect(env.MY_COWORK_API_KEY).toBeUndefined(); expect(env.OPENAI_API_KEY).toBeUndefined();
    expect(env.LARK_APP_SECRET).toBeUndefined(); expect(env.ELECTRON_RUN_AS_NODE).toBeUndefined();
    expect(env.MY_COWORK_DISABLE_CHANNELS).toBe('1');
  });
  it('creates consistent identities and refuses a nonempty destination', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'mcapp-init-'));
    const project = path.join(root, '中文 空格');
    cli.initProject(project, 'cn.example.inventory', '库存管理');
    const manifest = fs.readFileSync(path.join(project, 'mycowork-app.yaml'), 'utf8');
    expect(manifest).toContain('mcapp_cn_example_inventory.plugin:register');
    expect(fs.existsSync(path.join(project, 'backend/mcapp_cn_example_inventory/plugin.py'))).toBe(true);
    expect(fs.readFileSync(path.join(project, 'frontend/src/App.tsx'), 'utf8')).toContain('cn.example.inventory');
    expect(() => cli.initProject(project, 'cn.example.inventory', '库存管理')).toThrow('非空');
  });
});
