import { AppShell, Burger, Group, Kbd, NavLink, Stack, Text } from '@mantine/core';
import { useDisclosure, useHotkeys } from '@mantine/hooks';
import {
  IconChartBar,
  IconInbox,
  IconListDetails,
  IconPackage,
  IconSettings,
  type Icon,
} from '@tabler/icons-react';
import { useMemo } from 'react';
import { NavLink as RouterNavLink, Outlet } from 'react-router';
import { DashboardBar } from './DashboardBar';
import { QuickAddContext } from './QuickAddContext';
import { QuickExpenseModal } from './QuickExpenseModal';

interface NavItem {
  to: string;
  label: string;
  icon: Icon;
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: '/collect', label: '收集', icon: IconInbox },
  { to: '/expenses', label: '清单', icon: IconListDetails },
  { to: '/batches', label: '批次', icon: IconPackage },
  { to: '/stats', label: '统计', icon: IconChartBar },
  { to: '/settings', label: '设置', icon: IconSettings },
];

const NAVBAR_WIDTH = 176;
const HEADER_HEIGHT = 48;

function SideNav({ onNavigate }: { onNavigate: () => void }) {
  return (
    <Stack gap={2} p="xs">
      <Text fw={700} size="lg" px="sm" py="md" style={{ letterSpacing: '0.08em' }}>
        发票账本
      </Text>
      {NAV_ITEMS.map((item) => (
        <RouterNavLink key={item.to} to={item.to} onClick={onNavigate} style={{ textDecoration: 'none', color: 'inherit' }}>
          {({ isActive }) => (
            <NavLink
              component="span"
              className="nav-link"
              data-active={isActive || undefined}
              active={isActive}
              variant="subtle"
              label={item.label}
              leftSection={<item.icon size={18} stroke={1.6} />}
            />
          )}
        </RouterNavLink>
      ))}
      <Text size="xs" c="dimmed" px="sm" mt="xl">
        <Kbd size="xs">N</Kbd> 记一笔　<Kbd size="xs">/</Kbd> 搜索
      </Text>
    </Stack>
  );
}

export function AppShellLayout() {
  const [quickOpened, quick] = useDisclosure(false);
  const [navOpened, nav] = useDisclosure(false);
  useHotkeys([['n', quick.open]]);
  const contextValue = useMemo(() => ({ openQuickAdd: quick.open }), [quick.open]);

  return (
    <QuickAddContext.Provider value={contextValue}>
      <AppShell
        layout="alt"
        navbar={{ width: NAVBAR_WIDTH, breakpoint: 'sm', collapsed: { mobile: !navOpened } }}
        header={{ height: HEADER_HEIGHT }}
        styles={{
          main: { background: 'var(--paper-bg)', minWidth: 0 },
          navbar: { background: 'var(--paper-surface)', borderColor: 'var(--paper-line)' },
          header: { background: 'var(--paper-bg)', borderColor: 'var(--paper-line)' },
        }}
      >
        <AppShell.Header>
          <Group h="100%" px="lg" wrap="nowrap" style={{ overflow: 'hidden' }}>
            <Burger opened={navOpened} onClick={nav.toggle} hiddenFrom="sm" size="sm" aria-label="切换导航" />
            <DashboardBar />
          </Group>
        </AppShell.Header>
        <AppShell.Navbar>
          <SideNav onNavigate={nav.close} />
        </AppShell.Navbar>
        <AppShell.Main>
          <Outlet />
        </AppShell.Main>
      </AppShell>
      <QuickExpenseModal opened={quickOpened} onClose={quick.close} />
    </QuickAddContext.Provider>
  );
}
