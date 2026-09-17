import { Loader } from '@mantine/core';
import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router';
import { AppShellLayout } from './components/AppShellLayout';

const CollectPage = lazy(() => import('./pages/CollectPage').then((m) => ({ default: m.CollectPage })));
const ExpensesPage = lazy(() => import('./pages/ExpensesPage').then((m) => ({ default: m.ExpensesPage })));
const BatchesPage = lazy(() => import('./pages/BatchesPage').then((m) => ({ default: m.BatchesPage })));
const StatsPage = lazy(() => import('./pages/StatsPage').then((m) => ({ default: m.StatsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })));

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
          <Route path="*" element={<Navigate to="/expenses" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
