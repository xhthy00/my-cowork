/** @vitest-environment jsdom */
import { useEffect, useState } from 'react';
import { render, screen, cleanup, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { SkillPickerPanel } from '../../renderer/src/components/chat/PickerPanel';
import SkillListItem from '../../renderer/src/components/skills/SkillListItem';
import SkillsView from '../../renderer/src/components/skills/SkillsView';
import { usePageTabStore } from '../../renderer/src/store/pageTab';
import { appSkillIdsInText, tokenizeRichPlainText, isSafeSkillFolderName } from '../../renderer/src/lib/richText';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const key = 'app:cn.example.one:risk-analysis';
const skill = { id: key, name: '风险分析', description: '依据业务记录', enabled: true, scope: { isGlobal: true, selectedAgents: [] }, appOrigin: { id: 'cn.example.one', name: '插件一', version: '1.0.0' } };

it('preserves exact app identity in chips and extraction without weakening folder validation', () => {
  const text = `请用 #${key} 和 #app:cn.example.two:risk-analysis 分析`;
  expect(tokenizeRichPlainText(text).filter(row => row.type === 'skill').map(row => row.text)).toEqual([`#${key}`, '#app:cn.example.two:risk-analysis']);
  expect(appSkillIdsInText(text)).toEqual([key, 'app:cn.example.two:risk-analysis']);
  expect(appSkillIdsInText(text.replace(`#${key}`, ''))).toEqual(['app:cn.example.two:risk-analysis']);
  expect(isSafeSkillFolderName(key)).toBe(false);
});

it('selects and removes same-named skills independently', async () => {
  window.api = { ...window.api, getBackendUrl: vi.fn().mockResolvedValue('http://localhost:9000'), backendRequest: undefined } as typeof window.api;
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ skills: [skill, { ...skill, id: 'app:cn.example.two:risk-analysis', appOrigin: { ...skill.appOrigin, id: 'cn.example.two', name: '插件二' } }] }))));
  function Picker() {
    const [text, setText] = useState('');
    return <><output>{text}</output><SkillPickerPanel inputValue={text} onToggleItem={item => setText(value => value.includes(item.token) ? value.replace(item.token, '') : `${value} ${item.token}`)} /></>;
  }
  render(<Picker />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: /风险分析.*插件一/ }));
  await user.click(screen.getByRole('button', { name: /风险分析.*插件二/ }));
  expect(screen.getByRole('status').textContent).toContain(key);
  await user.click(screen.getByRole('button', { name: /风险分析.*插件一/ }));
  expect(appSkillIdsInText(screen.getByRole('status').textContent || '')).toEqual(['app:cn.example.two:risk-analysis']);
});

it('shows plugin-managed status instead of destructive independent controls', () => {
  render(<SkillListItem skill={skill} onToggle={vi.fn()} onScopeChange={vi.fn()} onDelete={vi.fn()} />);
  expect(screen.getByText(/插件一.*1.0.0/)).toBeTruthy();
  expect(screen.queryByRole('switch')).toBeNull();
  expect(screen.queryByRole('button', { name: '更多' })).toBeNull();
  expect(screen.queryByText('选择智能体访问权限')).toBeNull();
  expect(screen.getByRole('button', { name: '打开所属插件' })).toBeTruthy();
});

it('refreshes mounted skill cards when plugin maintenance finishes', async () => {
  let statusChanged: ((status: any) => void) | undefined;
  let version = '1.0.0';
  window.api = { ...window.api, getBackendUrl: vi.fn().mockResolvedValue('http://localhost:9000'), backendRequest: undefined,
    onIndustryStatus: (fn: typeof statusChanged) => { statusChanged = fn; return () => {}; } } as typeof window.api;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(String(url).endsWith('/api/skills') ? { skills: [{ ...skill, appOrigin: { ...skill.appOrigin, version } }] } : { skills: [] }))));
  render(<SkillsView />);
  expect(await screen.findByText(/插件一.*1.0.0/)).toBeTruthy();
  version = '1.1.0';
  await act(async () => { statusChanged?.({ busy: false }); });
  expect(await screen.findByText(/插件一.*1.1.0/)).toBeTruthy();
});

it('mounts the destination composer before sending a plugin skill draft', async () => {
  usePageTabStore.setState({ workspaceView: 'hub', hubTab: 'agents' });
  function Composer() {
    const [draft, setDraft] = useState('');
    useEffect(() => {
      const fill = (event: Event) => setDraft((event as CustomEvent<string>).detail);
      window.addEventListener('my-cowork:composer-fill', fill);
      return () => window.removeEventListener('my-cowork:composer-fill', fill);
    }, []);
    return <output>{draft}</output>;
  }
  function View() {
    const view = usePageTabStore(state => state.workspaceView);
    return view === 'workspace' ? <Composer /> : <SkillListItem skill={skill} onToggle={vi.fn()} onScopeChange={vi.fn()} />;
  }
  render(<View />);
  await userEvent.setup().click(screen.getByTitle('在对话中试用'));
  expect(screen.getByRole('status').textContent).toContain(`#${key}`);
});
