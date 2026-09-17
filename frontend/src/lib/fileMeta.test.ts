import { describe, expect, test } from 'vitest';
import { fileTypeOf, formatFileSize, middleEllipsis } from './fileMeta';

describe('fileMeta', () => {
  test('formatFileSize uses B / KB / MB with one decimal', () => {
    expect(formatFileSize(0)).toBe('0 B');
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(1536)).toBe('1.5 KB');
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB');
    expect(formatFileSize(-1)).toBe('0 B');
  });

  test('fileTypeOf detects by extension or mime', () => {
    expect(fileTypeOf('发票.PDF')).toBe('pdf');
    expect(fileTypeOf('截图.jpeg')).toBe('image');
    expect(fileTypeOf('scan', 'image/heic')).toBe('image');
    expect(fileTypeOf('e.xml')).toBe('xml');
    expect(fileTypeOf('e.ofd')).toBe('other');
    expect(fileTypeOf('noext')).toBe('other');
  });

  test('middleEllipsis keeps the start and the extension', () => {
    expect(middleEllipsis('short.pdf', 20)).toBe('short.pdf');
    expect(middleEllipsis('一个非常非常非常长的发票文件名称-2026年3月.pdf', 16)).toBe('一个非常非常非常…6年3月.pdf');
    expect(middleEllipsis('abcdefghijklmnopqrstuvwxyz', 10)).toBe('abcde…vwxyz');
  });
});
