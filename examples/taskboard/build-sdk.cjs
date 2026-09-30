// Keep this static example on the same SDK source as generated Vite projects.
const path = require('node:path');
const fs = require('node:fs');
const { spawnSync } = require('node:child_process');
const repo = path.resolve(__dirname, '../..');
const output = path.join(__dirname, 'frontend/dist');
const result = spawnSync(process.execPath, [require.resolve('typescript/bin/tsc'), path.join(repo, 'packages/app-sdk/src/index.ts'), '--target', 'ES2022', '--module', 'ES2022', '--skipLibCheck', '--outDir', output], { stdio: 'inherit' });
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status || 1);
fs.renameSync(path.join(output, 'index.js'), path.join(output, 'sdk.js'));
