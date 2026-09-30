import { useEffect, useState } from 'react';
import { createHost } from '@mycowork/app-sdk';
const host = createHost({ appId: '__APP_ID__' });
if (import.meta.hot) import.meta.hot.dispose(() => host.dispose());
type RecordItem = { id: number; title: string };
const draftKey = '__APP_ID__:draft';

export default function App() {
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [title, setTitle] = useState(() => sessionStorage.getItem(draftKey) || '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const refresh = () => host.request<{records: RecordItem[]}>('GET', '/records').then(data => setRecords(data.records));
  useEffect(() => {
    void refresh().catch(cause => setError(cause.message));
    const off = host.on('host.appearance', data => { document.documentElement.dataset.theme = data.theme; });
    void host.navigation.setRoute('/').catch(cause => setError(cause.message));
    return off;
  }, []);
  useEffect(() => { sessionStorage.setItem(draftKey, title); void host.ui.setDirty(Boolean(title)).catch(() => {}); }, [title]);
  async function save() {
    if (!title.trim() || saving) return;
    setSaving(true); setError('');
    try { await host.request('POST', '/records', { title }); setTitle(''); await refresh(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setSaving(false); }
  }
  return <main>
    <h1>{__APP_NAME_JSON__}</h1>
    <p>添加一条记录，退出后仍可继续使用。</p>
    <div className="entry"><input aria-label="记录内容" value={title} maxLength={200} onChange={event => setTitle(event.target.value)} placeholder="输入记录内容" /><button disabled={saving || !title.trim()} onClick={() => void save()}>{saving ? '正在保存' : '保存'}</button></div>
    {error && <p role="alert">{error} <button onClick={() => void refresh().then(() => setError('')).catch(cause => setError(cause.message))}>查看实际记录</button></p>}
    <ul>{records.map(record => <li key={record.id}>{record.title}</li>)}</ul>
    {!records.length && <p>暂无记录</p>}
  </main>;
}
