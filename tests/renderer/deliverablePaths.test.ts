import { expect, it, vi } from 'vitest';
import { recoverReferencedArtifacts, referencedDeliverables } from '../../renderer/src/lib/deliverablePaths';
import type { Message } from '../../renderer/src/store/session';

it('extracts real path candidates with Chinese, spaces, parentheses, Windows and file URLs', () => {
  const path = '/Users/me/Documents/AIS/调研 报告（2026年10月14日合并版）.html';
  expect(referencedDeliverables('交付文件：`' + path + '`')).toEqual([path]);
  expect(referencedDeliverables(`[报告](<${path}>)`)).toEqual([path]);
  expect(referencedDeliverables('[报告](file:///Users/me/%E6%8A%A5%E5%91%8A.html)')).toEqual(['/Users/me/报告.html']);
  expect(referencedDeliverables('`C:\\Users\\me\\Documents\\合并 报告.html`')).toEqual(['C:\\Users\\me\\Documents\\合并 报告.html']);
  expect(referencedDeliverables('https://example.com/report.html\n`/tmp/_gen.py`')).toEqual([]);
});

it('recovers only verified files on the correct final answer without rewriting previous artifacts', async () => {
  const messages: Message[] = [
    { id: 'u1', role: 'user', content: '生成报告' },
    { id: 'a1', role: 'assistant', content: '交付：`/tmp/报告 合并版.html`，草稿 `/tmp/missing.html`' },
    { id: 'u2', role: 'user', content: '分析别的问题' },
    { id: 'a2', role: 'assistant', content: '分析结论' },
    { id: 'u3', role: 'user', content: '已有产物' },
    { id: 'a3', role: 'assistant', content: '`/tmp/not-to-add.html`', artifacts: [{ path: '/tmp/existing.pdf', name: 'existing.pdf', kind: 'pdf' }] },
  ];
  const verify = vi.fn().mockResolvedValue(['/tmp/报告 合并版.html']);
  const recovered = await recoverReferencedArtifacts(messages, verify);
  expect(verify).toHaveBeenCalledWith(['/tmp/报告 合并版.html', '/tmp/missing.html']);
  expect([...recovered.keys()]).toEqual(['a1']);
  expect(recovered.get('a1')).toEqual([{ path: '/tmp/报告 合并版.html', name: '报告 合并版.html', kind: 'file' }]);
  expect(messages[1].artifacts).toBeUndefined();
});
