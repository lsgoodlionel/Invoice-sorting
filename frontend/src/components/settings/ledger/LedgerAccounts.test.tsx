import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AUTHENTICATED, SAAS_AUTHENTICATED } from '../../../test/authStatus';
import { mockFetch, type RecordedCall } from '../../../test/fetchMock';
import { renderWithProviders } from '../../../test/render';
import { LedgerTransferSection } from './LedgerTransferSection';

// 测试数据全部虚构
const ACCOUNTS_HINT = /备份文件包含登录账号与密码哈希/;
const RESTORE_NOTE =
  '同名账号的密码将恢复为备份时的密码；执行导入的管理员若在其中，导入后需用备份时的密码重新登录；本地多出的账号将被删除（执行导入的管理员本人除外）';
const MERGE_NOTE = '包内含 3 个账号，合并模式不导入账号';

const BASE_ITEMS = [
  { key: 'records', label: '记录', added: 12, skipped: 0, conflicts: 0, failed: 0, details: [], truncated: 0 },
  { key: 'attachments', label: '附件', added: 30, skipped: 0, conflicts: 0, failed: 0, details: [], truncated: 0 },
];

const MERGE_PREVIEW = {
  upload_id: 'up-1',
  status: 'ready',
  mode: 'merge',
  target_name: '默认账套',
  items: BASE_ITEMS,
  warnings: [],
  accounts: { count: 3, will_restore: false, note: MERGE_NOTE },
};

const REPLACE_PREVIEW = {
  ...MERGE_PREVIEW,
  mode: 'replace',
  items: [
    ...BASE_ITEMS,
    {
      key: 'accounts', label: '登录账号', added: 2, updated: 1, skipped: 0, deleted: 1, conflicts: 0, failed: 0, truncated: 0,
      details: [
        { action: 'updated', label: 'admin（管理员）', reason: '更新密码（恢复为备份时的密码）' },
        { action: 'added', label: 'alice（成员）', reason: '新建（可用备份时的密码登录）' },
        { action: 'added', label: 'bob（管理员）', reason: '新建（可用备份时的密码登录）' },
        { action: 'deleted', label: 'carol（成员）', reason: '备份里没有的本地账号，删除' },
      ],
    },
  ],
  accounts: { count: 3, will_restore: true, note: RESTORE_NOTE },
};

function routes(auth = AUTHENTICATED, extra: Record<string, unknown> = {}) {
  return mockFetch({
    'GET /api/auth/status': auth,
    'GET /api/license/status': { state: 'active', message: '' },
    'GET /api/backup/packages': [],
    'GET /api/quota': { enforced: true, is_readonly: false, readonly_message: '', limits: [] },
    'POST /api/backup/imports': { upload_id: 'up-1', part_size: 10 },
    'PUT /api/backup/imports/up-1/parts/0': null,
    'PUT /api/backup/imports/up-1/parts/1': null,
    'POST /api/backup/imports/up-1/complete': (call: RecordedCall) => ({
      data: (call.body as { mode?: string }).mode === 'replace' ? REPLACE_PREVIEW : MERGE_PREVIEW,
    }),
    'DELETE /api/backup/imports/up-1': null,
    ...extra,
  });
}

const zipFile = () => new File(['PK-0123456789-abc'], '账本备份.zip', { type: 'application/zip' });
const fileInput = () => document.querySelector('input[type="file"]') as HTMLInputElement;

async function uploadToPreview() {
  const user = userEvent.setup();
  await user.upload(fileInput(), zipFile());
  expect(await screen.findByText(/将新增 12 条记录、30 个附件/)).toBeInTheDocument();
  return user;
}

describe('备份与搬迁 · 登录账号', () => {
  test('single-tenant backup warns that accounts and password hashes are inside', async () => {
    routes(AUTHENTICATED);
    renderWithProviders(<LedgerTransferSection />);

    expect(await screen.findByText(ACCOUNTS_HINT)).toBeInTheDocument();
  });

  test('SaaS backup does not mention accounts', async () => {
    routes(SAAS_AUTHENTICATED);
    renderWithProviders(<LedgerTransferSection />);

    expect(await screen.findByText('服务器上还没有备份。')).toBeInTheDocument();
    expect(screen.queryByText(ACCOUNTS_HINT)).not.toBeInTheDocument();
  });

  test('merge preview says accounts are not imported', async () => {
    routes();
    renderWithProviders(<LedgerTransferSection />);

    await uploadToPreview();

    expect(screen.getByText(MERGE_NOTE)).toBeInTheDocument();
    expect(screen.queryByText(RESTORE_NOTE)).not.toBeInTheDocument();
    expect(within(screen.getByRole('table', { name: '导入明细' })).queryByText('登录账号')).not.toBeInTheDocument();
  });

  test('switching to replace re-previews and lists accounts with a prominent warning', async () => {
    const { calls } = routes();
    renderWithProviders(<LedgerTransferSection />);
    const user = await uploadToPreview();

    await user.click(screen.getByRole('radio', { name: /清空后整套覆盖/ }));

    expect(await screen.findByText(RESTORE_NOTE)).toBeInTheDocument();
    expect(screen.getByText('将恢复 3 个登录账号（含密码）')).toBeInTheDocument();
    const completes = calls.filter((call) => call.method === 'POST' && call.url.endsWith('/complete'));
    expect(completes.map((call) => call.body)).toEqual([{ include_settings: true }, { include_settings: true, mode: 'replace' }]);
    const table = screen.getByRole('table', { name: '导入明细' });
    expect(within(table).getByText('登录账号')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '登录账号 明细（4）' }));
    expect(screen.getByText('admin（管理员）：更新密码（恢复为备份时的密码）')).toBeInTheDocument();
    expect(screen.getAllByText('新增').length).toBeGreaterThan(0);
    expect(screen.getByText('更新')).toBeInTheDocument();
    expect(screen.getByText('删除')).toBeInTheDocument();
    expect(screen.getByText('carol（成员）：备份里没有的本地账号，删除')).toBeInTheDocument();
  });

  test('switching back to merge restores the merge preview', async () => {
    routes();
    renderWithProviders(<LedgerTransferSection />);
    const user = await uploadToPreview();

    await user.click(screen.getByRole('radio', { name: /清空后整套覆盖/ }));
    await screen.findByText(RESTORE_NOTE);
    await user.click(screen.getByRole('radio', { name: /合并到现有账本/ }));

    await waitFor(() => expect(screen.queryByText(RESTORE_NOTE)).not.toBeInTheDocument());
    expect(screen.getByText(MERGE_NOTE)).toBeInTheDocument();
  });

  test('result view confirms the accounts were restored', async () => {
    routes(AUTHENTICATED, {
      'POST /api/backup/imports/up-1/confirm': { upload_id: 'up-1', status: 'running', mode: 'replace' },
      'GET /api/backup/imports/up-1/status': {
        upload_id: 'up-1',
        status: 'done',
        mode: 'replace',
        report: { items: BASE_ITEMS, accounts: { count: 3, will_restore: true, note: '登录账号已恢复为备份时的状态' } },
      },
    });
    renderWithProviders(<LedgerTransferSection />);
    const user = await uploadToPreview();
    await user.click(screen.getByRole('radio', { name: /清空后整套覆盖/ }));
    await user.type(screen.getByRole('textbox', { name: /输入当前账套名称/ }), '默认账套');

    await user.click(screen.getByRole('button', { name: '清空并覆盖' }));

    expect(await screen.findByText('登录账号已恢复', {}, { timeout: 4000 })).toBeInTheDocument();
  });
});
