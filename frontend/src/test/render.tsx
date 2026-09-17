import { MantineProvider } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { CurrentUserProvider, type CurrentUserValue } from '../components/auth/CurrentUserContext';
import { theme } from '../theme';
import { ADMIN_USER } from './authStatus';

export const ADMIN_CONTEXT: CurrentUserValue = { user: ADMIN_USER, isAdmin: true, authEnabled: true };

export function createTestClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

interface TestProvidersProps {
  children: ReactNode;
  route?: string;
  client?: QueryClient;
  /** 当前登录用户上下文，默认管理员（AuthGate 内部会覆盖） */
  currentUser?: CurrentUserValue;
}

export function TestProviders({ children, route = '/', client, currentUser = ADMIN_CONTEXT }: TestProvidersProps) {
  return (
    <QueryClientProvider client={client ?? createTestClient()}>
      <MantineProvider theme={theme} env="test">
        <DatesProvider settings={{ locale: 'zh-cn' }}>
          <ModalsProvider>
            <Notifications />
            <CurrentUserProvider value={currentUser}>
              <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
            </CurrentUserProvider>
          </ModalsProvider>
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}

export function renderWithProviders(
  ui: ReactElement,
  options: { route?: string; client?: QueryClient; currentUser?: CurrentUserValue } = {},
) {
  return render(ui, { wrapper: ({ children }) => <TestProviders {...options}>{children}</TestProviders> });
}
