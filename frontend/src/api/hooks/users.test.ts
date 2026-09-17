import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { usersApi } from './users';

describe('usersApi', () => {
  test('sends contract payloads', async () => {
    const { calls } = mockFetch({
      'GET /api/users': [],
      'POST /api/users': {},
      'PATCH /api/users/3': {},
      'POST /api/users/3/password': null,
    });
    await usersApi.list();
    await usersApi.create({ username: 'lisi', display_name: '李四', password: 'password-1', role: 'member' });
    await usersApi.update(3, { is_active: false });
    await usersApi.resetPassword(3, 'password-2');
    expect(calls.map((c) => [c.method, c.url, c.body])).toEqual([
      ['GET', '/api/users', undefined],
      ['POST', '/api/users', { username: 'lisi', display_name: '李四', password: 'password-1', role: 'member' }],
      ['PATCH', '/api/users/3', { is_active: false }],
      ['POST', '/api/users/3/password', { password: 'password-2' }],
    ]);
  });
});
