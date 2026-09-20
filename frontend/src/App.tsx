import { Loader } from '@mantine/core';
import { Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router';
import { AppShellLayout } from './components/AppShellLayout';
import { lazyPage } from './lib/lazyPage';

const CollectPage = lazyPage(() => import('./pages/CollectPage'), 'CollectPage');
const ExpensesPage = lazyPage(() => import('./pages/ExpensesPage'), 'ExpensesPage');
const BatchesPage = lazyPage(() => import('./pages/BatchesPage'), 'BatchesPage');
const StatsPage = lazyPage(() => import('./pages/StatsPage'), 'StatsPage');
const SettingsPage = lazyPage(() => import('./pages/SettingsPage'), 'SettingsPage');
const PlatformPage = lazyPage(() => import('./pages/PlatformPage'), 'PlatformPage');

export function App() {
  return (
    <Suspense fallback={<Loader size="sm" m="xl" />}>
      <Routes>
        <Route element={<AppShellLayout />}>
          <Route index element={<Navigate to="/expenses" replace />} />
          <Route path="collect" element={<CollectPage />} />
          <Route path="expenses" element={<ExpensesPage />} />
          <Route path="batches" element={<BatchesPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="platform" element={<PlatformPage />} />
          <Route path="*" element={<Navigate to="/expenses" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
