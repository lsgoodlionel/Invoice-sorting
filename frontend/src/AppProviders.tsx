import { MantineProvider } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import 'dayjs/locale/zh-cn';
import { useState, type ReactNode } from 'react';
import { createQueryClient } from './queryClient';
import { theme } from './theme';

interface AppProvidersProps {
  children: ReactNode;
  client?: QueryClient;
}

export function AppProviders({ children, client }: AppProvidersProps) {
  const [queryClient] = useState(() => client ?? createQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <DatesProvider settings={{ locale: 'zh-cn', firstDayOfWeek: 1 }}>
          <ModalsProvider labels={{ confirm: '确定', cancel: '取消' }}>
            <Notifications position="top-right" limit={4} />
            {children}
          </ModalsProvider>
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}
