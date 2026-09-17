import { MantineProvider } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { theme } from '../theme';

export function createTestClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function TestProviders({ children, route = '/', client }: { children: ReactNode; route?: string; client?: QueryClient }) {
  return (
    <QueryClientProvider client={client ?? createTestClient()}>
      <MantineProvider theme={theme} env="test">
        <DatesProvider settings={{ locale: 'zh-cn' }}>
          <ModalsProvider>
            <Notifications />
            <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
          </ModalsProvider>
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}

export function renderWithProviders(ui: ReactElement, options: { route?: string; client?: QueryClient } = {}) {
  return render(ui, { wrapper: ({ children }) => <TestProviders {...options}>{children}</TestProviders> });
}
