import { describe, expect, test } from 'vitest';
import { mockFetch, type RecordedCall } from '../test/fetchMock';
import { hashFile, uploadLedgerPackage, uploadParts } from './ledgerUpload';

const CONTENT = 'PK-ledger-package-0123456789';
const makeFile = () => new File([CONTENT], '账本.zip', { type: 'application/zip' });
const partCalls = (calls: RecordedCall[]) => calls.filter((call) => call.method === 'PUT');
const blobText = (body: unknown) => (body as Blob).text();

const PREVIEW = { upload_id: 'up-1', items: [] };

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

describe('hashFile', () => {
  test('hashes the file in slices and reports progress', async () => {
    const progress: number[] = [];

    const digest = await hashFile(makeFile(), { readBytes: 10, onProgress: (done) => progress.push(done) });

    expect(digest).toBe(await sha256Hex(CONTENT));
    expect(progress).toEqual([10, 20, CONTENT.length]);
  });
});

describe('uploadParts', () => {
  test('sends every part in order with the agreed part size', async () => {
    // Arrange
    const { calls } = mockFetch({
      'PUT /api/backup/imports/up-1/parts/0': null,
      'PUT /api/backup/imports/up-1/parts/1': null,
      'PUT /api/backup/imports/up-1/parts/2': null,
    });
    const uploaded: number[] = [];

    // Act
    await uploadParts('up-1', makeFile(), { partSize: 12, onProgress: (bytes) => uploaded.push(bytes) });

    // Assert
    const puts = partCalls(calls);
    expect(puts.map((call) => call.url)).toEqual([
      '/api/backup/imports/up-1/parts/0',
      '/api/backup/imports/up-1/parts/1',
      '/api/backup/imports/up-1/parts/2',
    ]);
    expect(await Promise.all(puts.map((call) => blobText(call.body)))).toEqual([
      CONTENT.slice(0, 12),
      CONTENT.slice(12, 24),
      CONTENT.slice(24),
    ]);
    expect(uploaded).toEqual([12, 24, CONTENT.length]);
  });

  test('retries a failed part twice before moving on', async () => {
    let attempts = 0;
    const { calls } = mockFetch({
      'PUT /api/backup/imports/up-1/parts/0': () => {
        attempts += 1;
        return attempts <= 2 ? { status: 502, error: '网关超时' } : { data: null };
      },
      'PUT /api/backup/imports/up-1/parts/1': null,
    });

    await uploadParts('up-1', makeFile(), { partSize: 16, retryDelayMs: 0 });

    expect(partCalls(calls).map((call) => call.url.split('/').at(-1))).toEqual(['0', '0', '0', '1']);
  });

  test('gives up with the server message after three failed attempts', async () => {
    const { calls } = mockFetch({
      'PUT /api/backup/imports/up-1/parts/0': () => ({ status: 500, error: '磁盘已满' }),
    });

    await expect(uploadParts('up-1', makeFile(), { partSize: 16, retryDelayMs: 0 })).rejects.toThrow('磁盘已满');
    expect(partCalls(calls)).toHaveLength(3);
  });

  test('stops without retrying once aborted', async () => {
    const { calls } = mockFetch({ 'PUT /api/backup/imports/up-1/parts/0': null });
    const controller = new AbortController();
    controller.abort();

    await expect(uploadParts('up-1', makeFile(), { partSize: 16, signal: controller.signal })).rejects.toThrow();
    expect(partCalls(calls)).toHaveLength(0);
  });
});

describe('uploadLedgerPackage', () => {
  test('registers the upload with the file hash, sends parts, then asks for the preview', async () => {
    const { calls } = mockFetch({
      'POST /api/backup/imports': { upload_id: 'up-1', part_size: 20 },
      'PUT /api/backup/imports/up-1/parts/0': null,
      'PUT /api/backup/imports/up-1/parts/1': null,
      'POST /api/backup/imports/up-1/complete': PREVIEW,
    });
    const stages: string[] = [];

    const preview = await uploadLedgerPackage(makeFile(), {
      signal: new AbortController().signal,
      onStage: (stage) => stages.push(stage),
      onPercent: () => undefined,
      onCreated: () => undefined,
    });

    expect(preview).toEqual(PREVIEW);
    expect(calls[0].body).toEqual({
      filename: '账本.zip',
      size: CONTENT.length,
      part_size: 8 * 1024 * 1024,
      sha256: await sha256Hex(CONTENT),
    });
    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([
      'POST /api/backup/imports',
      'PUT /api/backup/imports/up-1/parts/0',
      'PUT /api/backup/imports/up-1/parts/1',
      'POST /api/backup/imports/up-1/complete',
    ]);
    expect(stages).toEqual(['hashing', 'uploading', 'analyzing']);
  });
});
