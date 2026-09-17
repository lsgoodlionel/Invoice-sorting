import { useQuery } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import { render } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { AppProviders } from './AppProviders';
import { api } from './api/client';
import { createQueryClient } from './queryClient';
import { mockFetch } from './test/fetchMock';

function Probe() {
  useQuery({ queryKey: ['probe'], queryFn: () => api.get('/probe'), retry: false });
  return null;
}

describe('global error notifications', () => {
  test('shows backend Chinese error message when a query fails', async () => {
    mockFetch({ 'GET /api/probe': () => ({ status: 400, error: '参数不合法' }) });
    render(
      <AppProviders client={createQueryClient()}>
        <Probe />
      </AppProviders>,
    );
    expect(await screen.findByText('参数不合法', {}, { timeout: 3000 })).toBeInTheDocument();
  });
});
