/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ContextUsageIndicator from '../../renderer/src/components/chat/ContextUsageIndicator';
import ChatModelSelect from '../../renderer/src/components/chat/ChatModelSelect';

const state = vi.hoisted(() => ({active: null as any}));
vi.mock('@/hooks/useModels', () => ({
  useModels: () => ({active: state.active, models: {profiles: [state.active], activeId: state.active?.id},
    setActive: vi.fn(), switching: false, status: ''}),
  navigateToModelsConfig: vi.fn(),
}));

it('shows unknown capacity without inventing a percentage', () => {
  render(<ContextUsageIndicator used={3700} limit={0} />);
  const status = screen.getByRole('status');
  expect(status).toHaveAttribute('aria-label', '约 3.7K tokens · 上下文窗口未知');
  expect(status).not.toHaveAttribute('aria-valuenow');
  expect(status).toHaveAttribute('tabindex', '0');
});

it('refreshes capacity from local metadata when changing models, and clears stale capacity', async () => {
  const savedApi = window.api, savedFetch = globalThis.fetch;
  window.api = {...window.api, getBackendUrl: vi.fn().mockResolvedValue('http://localhost:8000')};
  const fetcher = vi.fn().mockImplementation(async (_url, init) => {
    const model = JSON.parse(init.body).model;
    return {ok: true, json: async () => ({context_limit: model === 'deepseek-flash' ? 1_000_000 : null})};
  });
  globalThis.fetch = fetcher;
  const update = vi.fn();
  state.active = {id: 'cloud', provider: 'openai_compat', name: 'DeepSeek', model: 'deepseek-flash', baseUrl: 'https://api.deepseek.com'};
  try {
    const {rerender} = render(<ChatModelSelect onContextChange={update} />);
    await waitFor(() => expect(update).toHaveBeenLastCalledWith(expect.objectContaining({model: 'deepseek-flash', limit: 1_000_000})));
    state.active = {id: 'local', provider: 'ollama', name: 'Local', model: 'unknown', baseUrl: 'http://localhost:11434/v1'};
    rerender(<ChatModelSelect onContextChange={update} />);
    await waitFor(() => expect(update).toHaveBeenLastCalledWith(expect.objectContaining({model: 'unknown', limit: 0})));
    expect(fetcher).toHaveBeenLastCalledWith('http://localhost:8000/api/model/info', expect.objectContaining({method: 'POST'}));
    expect(JSON.parse(fetcher.mock.calls.at(-1)![1].body)).not.toHaveProperty('api_key');
  } finally {
    globalThis.fetch = savedFetch; window.api = savedApi;
  }
});
