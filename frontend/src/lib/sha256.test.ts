import { describe, expect, test } from 'vitest';
import { createSha256 } from './sha256';

const encode = (text: string) => new TextEncoder().encode(text);

/** 参照实现：浏览器 Web Crypto 一次性计算的摘要 */
async function referenceHex(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function hashText(text: string): string {
  const hasher = createSha256();
  hasher.update(encode(text));
  return hasher.digestHex();
}

describe('createSha256', () => {
  test('matches the standard test vectors', () => {
    expect(hashText('')).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    expect(hashText('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
    expect(hashText('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq')).toBe(
      '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1',
    );
  });

  test('gives the same digest when fed in uneven pieces', async () => {
    // Arrange
    const bytes = Uint8Array.from({ length: 1000 }, (_, index) => (index * 31 + 7) % 256);
    const expected = await referenceHex(bytes);
    const hasher = createSha256();

    // Act
    [0, 1, 63, 64, 65, 200, 1000].reduce((start, end) => {
      hasher.update(bytes.subarray(start, end));
      return end;
    }, 0);

    // Assert
    expect(hasher.digestHex()).toBe(expected);
  });

  test('handles lengths around the padding boundary', async () => {
    for (const length of [55, 56, 57, 63, 64, 119, 120]) {
      const text = 'x'.repeat(length);
      expect(hashText(text)).toBe(await referenceHex(encode(text)));
    }
  });
});
