import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { marked } from 'marked';
const folder=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const source=await fs.readFile(path.join(folder,'MyCoWork统一推广文章.md'),'utf8');
const body=marked.parse(source);
await fs.writeFile(path.join(folder,'MyCoWork图文推广文章.html'),`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MyCoWork 图文推广文章</title>
<style>:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f5fbff;color:#233e50;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.85}main{max-width:1040px;margin:40px auto;padding:48px;background:white;border:1px solid #c9e2f1;border-radius:22px}h1{font-size:34px;line-height:1.45;margin:0 0 28px;text-wrap:balance}h2{font-size:28px;line-height:1.5;margin:48px 0 22px;border-top:1px solid #c9e2f1;padding-top:30px}h3{font-size:22px;line-height:1.6;margin:34px 0 16px}p,li{font-size:17px}img{display:block;max-width:100%;height:auto;margin:24px auto;border-radius:12px}a{color:#007ac5}table{width:100%;border-collapse:collapse;font-size:15px;display:block;overflow:auto}th,td{padding:12px 16px;border:1px solid #c9e2f1;text-align:left}th{background:#e1f3ff;white-space:nowrap}blockquote{margin:20px 0;padding:1px 20px;border-left:4px solid #007ac5;background:#f5fbff}pre{padding:20px;border-radius:12px;background:#edf7fd;overflow:auto}code{font-family:ui-monospace,monospace;font-size:14px}em{font-size:14px;color:#526c7e}footer{border-top:1px solid #c9e2f1;margin-top:40px;padding-top:20px;font-size:14px;color:#526c7e}@media(max-width:700px){main{margin:0;padding:24px 18px;border:0;border-radius:0}h1{font-size:27px}h2{font-size:24px}h3{font-size:20px}p,li{font-size:16px}}@media print{body{background:white}main{margin:0;border:0;padding:0}h2,h3{break-after:avoid}img,table{break-inside:avoid}}</style></head>
<body><main>${body}<footer>图文稿与图片位于同一素材目录；发布平台中请按图注顺序上传对应 PNG。</footer></main></body></html>`);
console.log('Generated standalone article preview (local image references).');
