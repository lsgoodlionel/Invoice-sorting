import { describe, expect, test } from 'vitest';
import type { ImportReportItem } from '../api/hooks/backup';
import type { LicenseStatus, QuotaStatus } from '../api/types';
import { importBlockReason, packageFileError, packageSource, previewHeadline, reportLabel, MAX_PACKAGE_BYTES } from './ledgerTransfer';

const item = (key: ImportReportItem['key'], added: number, skipped = 0, conflicts = 0): ImportReportItem => ({ key, added, skipped, conflicts });

const LICENSE = { state: 'active', message: '' } as LicenseStatus;
const QUOTA = { enforced: true, is_readonly: false, readonly_message: '' } as QuotaStatus;

describe('reportLabel', () => {
  test('prefers the server label, then a known name, then the raw key', () => {
    expect(reportLabel({ key: 'rules', label: '凭证规则（含关键词）' })).toBe('凭证规则（含关键词）');
    expect(reportLabel({ key: 'records' })).toBe('记录');
    expect(reportLabel({ key: 'memories' })).toBe('分类记忆');
    expect(reportLabel({ key: 'timeline' })).toBe('timeline');
  });
});

describe('packageSource', () => {
  const SOURCE = { tenant: '客户甲', exported_by: '张三', app_version: '0.2.1' };

  test('accepts a flat source or the whole ledger.json', () => {
    expect(packageSource(SOURCE)).toEqual(SOURCE);
    expect(packageSource({ kind: 'ledger', source: SOURCE })).toEqual(SOURCE);
  });

  test('treats missing or empty sources as a legacy package', () => {
    expect(packageSource(null)).toBeNull();
    expect(packageSource({})).toBeNull();
    expect(packageSource({ kind: 'ledger', source: null })).toBeNull();
  });
});

describe('previewHeadline', () => {
  test('summarises new records, attachments, duplicates and conflicts', () => {
    const items = [item('records', 12, 3), item('attachments', 30, 5), item('categories', 1, 2, 1)];

    expect(previewHeadline(items)).toBe('将新增 12 条记录、30 个附件，跳过 10 项重复，1 项冲突需要留意');
  });

  test('says so when nothing will change', () => {
    expect(previewHeadline([item('records', 0, 4)])).toBe('将新增 0 条记录、0 个附件，跳过 4 项重复');
  });
});

describe('packageFileError', () => {
  test('accepts a zip package', () => {
    expect(packageFileError(new File(['PK'], 'ledger.ZIP'))).toBeNull();
  });

  test('rejects other file types, empty files and oversized packages', () => {
    expect(packageFileError(new File(['x'], 'ledger.rar'))).toBe('只能导入 .zip 搬迁包');
    expect(packageFileError(new File([], 'ledger.zip'))).toBe('文件是空的');
    const huge = { name: 'big.zip', size: MAX_PACKAGE_BYTES + 1 } as File;
    expect(packageFileError(huge)).toMatch(/超过 2 GB/);
  });
});

describe('importBlockReason', () => {
  test('allows import when neither license nor quota is read-only', () => {
    expect(importBlockReason(LICENSE, QUOTA)).toBeNull();
    expect(importBlockReason(undefined, undefined)).toBeNull();
  });

  test('explains a lapsed license', () => {
    expect(importBlockReason({ ...LICENSE, state: 'readonly', message: '授权已过期' }, QUOTA)).toBe('授权已过期');
  });

  test('explains a suspended ledger', () => {
    expect(importBlockReason(LICENSE, { ...QUOTA, is_readonly: true, readonly_message: '账套已停用' })).toBe('账套已停用');
  });
});
