import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { SAAS_AUTHENTICATED } from '../../../test/authStatus';
import { mockFetch, type RecordedCall } from '../../../test/fetchMock';
import { renderWithProviders } from '../../../test/render';
import { LedgerTransferSection } from './LedgerTransferSection';

const LICENSE_OK = { state: 'active', message: '' };
const QUOTA_OK = { enforced: true, is_readonly: false, readonly_message: '', limits: [] };

const PREVIEW = {
  upload_id: 'up-1',
  status: 'ready',
  target_name: '阿尔法账套',
  source: { kind: 'ledger', source: { tenant: '客户甲', exported_by: '张三', app_version: '0.2.1' } },
  items: [
    { key: 'records', label: '记录', added: 12, skipped: 3, conflicts: 0, failed: 0, details: [], truncated: 0 },
    { key: 'attachments', label: '附件', added: 30, skipped: 5, conflicts: 0, failed: 0, details: [], truncated: 0 },
    {
      key: 'rules', label: '凭证规则', added: 0, skipped: 1, conflicts: 1, failed: 0, truncated: 0,
      details: [{ action: 'conflict', label: '规则“大额差旅”', reason: '与本地不同，保留本地' }],
    },
  ],
  warnings: [],
};

const DONE_JOB = {
  upload_id: 'up-1',
  status: 'done',
  mode: 'merge',
  report: {
    items: [
      {
        key: 'records', label: '记录', added: 12, skipped: 3, conflicts: 0, failed: 0, truncated: 2,
        details: [{ action: 'skipped', label: '发票 04403', reason: '已存在，跳过' }],
      },
    ],
  },
};

type Routes = Record<string, unknown>;

function routes(extra: Routes = {}) {
  return mockFetch({
    'GET /api/auth/status': SAAS_AUTHENTICATED,
    'GET /api/license/status': LICENSE_OK,
    'GET /api/backup/snapshots': [],
    'GET /api/quota': QUOTA_OK,
    'POST /api/backup/imports': { upload_id: 'up-1', part_size: 10 },
    'PUT /api/backup/imports/up-1/parts/0': null,
    'PUT /api/backup/imports/up-1/parts/1': null,
    'POST /api/backup/imports/up-1/complete': PREVIEW,
    'DELETE /api/backup/imports/up-1': null,
    ...extra,
  });
}

const zipFile = () => new File(['PK-0123456789-abc'], '账本搬迁包.zip', { type: 'application/zip' });
const fileInput = () => document.querySelector('input[type="file"]') as HTMLInputElement;
const callsTo = (calls: RecordedCall[], method: string, url: string) =>
  calls.filter((call) => call.method === method && call.url === url);

async function uploadToPreview(user = userEvent.setup()) {
  await user.upload(fileInput(), zipFile());
  expect(await screen.findByText(/将新增 12 条记录、30 个附件/)).toBeInTheDocument();
  return user;
}

describe('LedgerTransferSection · 导出', () => {
  test('starts an export without packages and downloads the finished file', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const { calls } = routes({
      'POST /api/backup/export-tenant': { job: 'j1', status: 'running', download_url: '' },
      'GET /api/backup/export-tenant/j1/status': {
        job: 'j1', status: 'done', file: 'ledger.zip', size: 3 * 1024 * 1024, download_url: '/api/backup/export-tenant/j1/download',
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<LedgerTransferSection />);

    await user.click(screen.getByRole('checkbox', { name: '不含资料包' }));
    await user.click(screen.getByRole('button', { name: '导出账本' }));

    const link = await screen.findByRole('link', { name: /下载 ledger\.zip（3\.0 MB）/ });
    expect(link).toHaveAttribute('href', '/api/backup/export-tenant/j1/download');
    expect(callsTo(calls, 'POST', '/api/backup/export-tenant')[0].body).toEqual({ include_packages: false });
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
  });

  test('shows the server reason when the export job fails', async () => {
    routes({
      'POST /api/backup/export-tenant': { job: 'j2', status: 'running', download_url: '' },
      'GET /api/backup/export-tenant/j2/status': { job: 'j2', status: 'failed', download_url: '', error: '磁盘空间不足，无法打包' },
    });
    renderWithProviders(<LedgerTransferSection />);

    await userEvent.click(screen.getByRole('button', { name: '导出账本' }));

    expect(await screen.findByText('磁盘空间不足，无法打包')).toBeInTheDocument();
  });

  test('shows the server message when starting the export is refused', async () => {
    routes({ 'POST /api/backup/export-tenant': () => ({ status: 409, error: '已有导出任务在进行' }) });
    renderWithProviders(<LedgerTransferSection />);

    await userEvent.click(screen.getByRole('button', { name: '导出账本' }));

    expect(await screen.findByText('已有导出任务在进行')).toBeInTheDocument();
  });
});

describe('LedgerTransferSection · 导入', () => {
  test('uploads in parts and shows the preview report', async () => {
    const { calls } = routes();
    renderWithProviders(<LedgerTransferSection />);

    await uploadToPreview();

    expect(calls.filter((call) => call.url.startsWith('/api/backup/imports')).map((call) => `${call.method} ${call.url}`)).toEqual([
      'POST /api/backup/imports',
      'PUT /api/backup/imports/up-1/parts/0',
      'PUT /api/backup/imports/up-1/parts/1',
      'POST /api/backup/imports/up-1/complete',
    ]);
    expect(screen.getByText(/账本搬迁包\.zip/)).toBeInTheDocument();
    expect(screen.getByText(/来自 客户甲 · 张三导出 · v0\.2\.1/)).toBeInTheDocument();
    const table = screen.getByRole('table');
    expect(within(table).getByText('记录')).toBeInTheDocument();
    expect(within(table).getByText('凭证规则')).toBeInTheDocument();
    expect(screen.getByText(/1 项冲突需要留意/)).toBeInTheDocument();
  });

  test('merges by default, polls the job and shows the result with details', async () => {
    let polls = 0;
    const { calls } = routes({
      'POST /api/backup/imports/up-1/confirm': { upload_id: 'up-1', status: 'running', mode: 'merge' },
      'GET /api/backup/imports/up-1/status': () => {
        polls += 1;
        return { data: polls === 1 ? { upload_id: 'up-1', status: 'running', mode: 'merge', progress: 40, message: '正在写入附件' } : DONE_JOB };
      },
    });
    renderWithProviders(<LedgerTransferSection />);
    const user = await uploadToPreview();

    expect(screen.getByRole('radio', { name: /合并到现有账本/ })).toBeChecked();
    await user.click(screen.getByRole('button', { name: '确认导入' }));

    expect(await screen.findByText('正在写入附件')).toBeInTheDocument();
    expect(await screen.findByText('导入完成', {}, { timeout: 4000 })).toBeInTheDocument();
    expect(callsTo(calls, 'POST', '/api/backup/imports/up-1/confirm')[0].body).toEqual({ mode: 'merge' });
    await user.click(screen.getByRole('button', { name: '记录 明细（1）' }));
    expect(screen.getByText('发票 04403：已存在，跳过')).toBeInTheDocument();
    expect(screen.getByText('另有 2 条未列出')).toBeInTheDocument();
  });

  test('replace mode needs the exact ledger name before it can be submitted', async () => {
    const { calls } = routes({
      'POST /api/backup/imports/up-1/confirm': { upload_id: 'up-1', status: 'running', mode: 'replace' },
      'GET /api/backup/imports/up-1/status': { ...DONE_JOB, mode: 'replace', backup_file: '备份/阿尔法账套-20260921.zip' },
    });
    renderWithProviders(<LedgerTransferSection />);
    const user = await uploadToPreview();

    await user.click(screen.getByRole('radio', { name: /清空后整套覆盖/ }));
    expect(screen.getByText(/会先自动备份/)).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: '清空并覆盖' });
    expect(submit).toBeDisabled();
    const nameInput = screen.getByRole('textbox', { name: /输入当前账套名称/ });
    await user.type(nameInput, '阿尔法');
    expect(submit).toBeDisabled();
    await user.type(nameInput, '账套');
    expect(submit).toBeEnabled();
    await user.click(submit);

    await waitFor(() =>
      expect(callsTo(calls, 'POST', '/api/backup/imports/up-1/confirm')[0]?.body).toEqual({ mode: 'replace', confirm_name: '阿尔法账套' }),
    );
    expect(await screen.findByText(/备份\/阿尔法账套-20260921\.zip/)).toBeInTheDocument();
  });

  test('cancelling during upload aborts and cleans up on the server', async () => {
    const { calls, fetchMock } = routes();
    const passThrough = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input, init) =>
      String(input).includes('/parts/')
        ? new Promise((_, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))))
        : passThrough(input, init),
    );
    const user = userEvent.setup();
    renderWithProviders(<LedgerTransferSection />);

    await user.upload(fileInput(), zipFile());
    await user.click(await screen.findByRole('button', { name: '取消上传' }));

    await waitFor(() => expect(callsTo(calls, 'DELETE', '/api/backup/imports/up-1')).toHaveLength(1));
    expect(await screen.findByText(/拖入账本搬迁包/)).toBeInTheDocument();
  });

  test('warns before leaving the page while uploading', async () => {
    const { fetchMock } = routes();
    const passThrough = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input, init) =>
      String(input).includes('/parts/') ? new Promise(() => undefined) : passThrough(input, init),
    );
    renderWithProviders(<LedgerTransferSection />);

    await userEvent.upload(fileInput(), zipFile());
    await screen.findByRole('button', { name: '取消上传' });

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  test('cancelling at the preview deletes the upload', async () => {
    const { calls } = routes();
    renderWithProviders(<LedgerTransferSection />);
    const user = await uploadToPreview();

    await user.click(screen.getByRole('button', { name: '放弃导入' }));

    await waitFor(() => expect(callsTo(calls, 'DELETE', '/api/backup/imports/up-1')).toHaveLength(1));
  });

  test('rejects files that are not zip packages', async () => {
    const { calls } = routes();
    renderWithProviders(<LedgerTransferSection />);

    await userEvent.setup({ applyAccept: false }).upload(fileInput(), new File(['x'], 'ledger.rar'));

    expect(await screen.findByText('只能导入 .zip 搬迁包')).toBeInTheDocument();
    expect(callsTo(calls, 'POST', '/api/backup/imports')).toHaveLength(0);
  });
});

async function expectImportDisabled(calls: RecordedCall[]) {
  expect(screen.getByLabelText('选择账本搬迁包')).toHaveAttribute('data-disabled');
  await userEvent.upload(fileInput(), zipFile());
  expect(callsTo(calls, 'POST', '/api/backup/imports')).toHaveLength(0);
  expect(screen.queryByRole('button', { name: '取消上传' })).not.toBeInTheDocument();
}

describe('LedgerTransferSection · 只读', () => {
  test('disables import but keeps export when the ledger is read-only', async () => {
    const { calls } = routes({ 'GET /api/quota': { ...QUOTA_OK, is_readonly: true, readonly_message: '账套已停用，数据只读' } });
    renderWithProviders(<LedgerTransferSection />);

    expect(await screen.findByText(/账套已停用，数据只读/)).toBeInTheDocument();
    await expectImportDisabled(calls);
    expect(screen.getByRole('button', { name: '导出账本' })).toBeEnabled();
  });

  test('disables import when the license has lapsed', async () => {
    const { calls } = routes({ 'GET /api/license/status': { state: 'readonly', message: '授权已过期，系统只读' } });
    renderWithProviders(<LedgerTransferSection />);

    expect(await screen.findByText(/授权已过期，系统只读/)).toBeInTheDocument();
    await expectImportDisabled(calls);
  });
});
