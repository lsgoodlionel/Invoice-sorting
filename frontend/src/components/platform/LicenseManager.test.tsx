import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch, type RecordedCall } from '../../test/fetchMock';
import { makeLicense } from '../../test/platformFixtures';
import { renderWithProviders } from '../../test/render';
import { LicenseManager } from './LicenseManager';

type Routes = Record<string, unknown>;

const RECORDS = [
  makeLicense(),
  makeLicense({ id: 2, customer_name: '某某医院', status: 'revoked', bound_instance_id: 'instance-abc', valid_until: null }),
];

function setup(extra: Routes = {}) {
  const result = mockFetch({ 'GET /api/platform/licenses': RECORDS, ...extra });
  renderWithProviders(<LicenseManager />);
  return result;
}

const findCall = (calls: RecordedCall[], method: string, url: string) =>
  calls.find((call) => call.method === method && call.url.split('?')[0] === url);

describe('授权列表', () => {
  test('只显示脱敏后的密钥与绑定状态', async () => {
    setup();

    const row = await screen.findByTestId('license-row-1');
    expect(within(row).getByText('ABCD****WXYZ')).toBeInTheDocument();
    expect(within(row).getByText('未绑定')).toBeInTheDocument();
    expect(within(row).getByText('有效')).toBeInTheDocument();
    const revoked = screen.getByTestId('license-row-2');
    expect(within(revoked).getByText('已吊销')).toBeInTheDocument();
    expect(within(revoked).getByText('instance-abc')).toBeInTheDocument();
    expect(within(revoked).getByText('永久')).toBeInTheDocument();
  });

  test('未绑定实例时解绑按钮不可用', async () => {
    setup();

    const row = await screen.findByTestId('license-row-1');
    expect(within(row).getByRole('button', { name: '解绑授权 1' })).toBeDisabled();
    expect(within(screen.getByTestId('license-row-2')).getByRole('button', { name: '解绑授权 2' })).toBeEnabled();
  });
});

describe('签发授权', () => {
  test('签发后只展示一次密钥原文', async () => {
    const user = userEvent.setup();
    const issued = makeLicense({ id: 3, license_key: 'FULL-KEY-1234-5678', is_key_visible: true });
    const { calls } = setup({ 'POST /api/platform/licenses': issued });
    await user.click(await screen.findByRole('button', { name: '签发授权' }));
    const dialog = await screen.findByRole('dialog', { name: '签发授权' });

    await user.type(within(dialog).getByLabelText('客户名称'), '某某学院');
    await user.type(within(dialog).getByLabelText('有效期至'), '2027-12-31');
    await user.click(within(dialog).getByRole('button', { name: '签发授权' }));

    expect(await screen.findByTestId('issued-license-key')).toHaveTextContent('FULL-KEY-1234-5678');
    expect(findCall(calls, 'POST', '/api/platform/licenses')?.body).toEqual({
      customer_name: '某某学院',
      max_users: 0,
      valid_until: '2027-12-31',
      note: '',
    });
  });

  test('没填客户名时不能提交', async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole('button', { name: '签发授权' }));
    const dialog = await screen.findByRole('dialog', { name: '签发授权' });

    expect(within(dialog).getByRole('button', { name: '签发授权' })).toBeDisabled();
  });
});

describe('吊销与解绑', () => {
  test('吊销发出 status=revoked', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/platform/licenses/1': makeLicense({ status: 'revoked' }) });
    const row = await screen.findByTestId('license-row-1');

    await user.click(within(row).getByRole('button', { name: '吊销授权 1' }));

    await waitFor(() =>
      expect(findCall(calls, 'PATCH', '/api/platform/licenses/1')?.body).toEqual({ status: 'revoked' }),
    );
  });

  test('解绑实例后可换机', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/platform/licenses/2/unbind': makeLicense({ id: 2, bound_instance_id: '' }) });
    const row = await screen.findByTestId('license-row-2');

    await user.click(within(row).getByRole('button', { name: '解绑授权 2' }));

    await waitFor(() => expect(findCall(calls, 'POST', '/api/platform/licenses/2/unbind')).toBeDefined());
  });

  test('后端拒绝时显示原文', async () => {
    const user = userEvent.setup();
    setup({ 'DELETE /api/platform/licenses/1': () => ({ status: 409, error: '该授权仍在使用' }) });
    const row = await screen.findByTestId('license-row-1');

    await user.click(within(row).getByRole('button', { name: '删除授权 1' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('该授权仍在使用');
  });
});
