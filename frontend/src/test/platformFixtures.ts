import type {
  ExportJob,
  LicenseRecord,
  LicenseStatus,
  Plan,
  PlatformOverview,
  PlatformTenant,
  PlatformTenantPage,
  QuotaStatus,
} from '../api/types';

export const OVERVIEW: PlatformOverview = {
  tenants: 2,
  active_tenants: 1,
  accounts: 4,
  storage_bytes: 1024 * 1024 * 3,
  expenses_created: 12,
};

export function makeTenant(overrides: Partial<PlatformTenant> = {}): PlatformTenant {
  return {
    slug: 'alpha',
    name: '阿尔法账套',
    status: 'active',
    plan: { code: 'team', name: '团队版' },
    expires_on: '2027-01-31',
    member_count: 3,
    usage: { day: '2026-09-20', users: 3, storage_bytes: 1024 * 1024, expenses_created: 7 },
    created_at: '2026-09-01T10:00:00+08:00',
    ...overrides,
  };
}

export function makeTenantPage(items: PlatformTenant[], overrides: Partial<PlatformTenantPage> = {}): PlatformTenantPage {
  return { items, total: items.length, page: 1, page_size: 20, ...overrides };
}

export function makePlan(overrides: Partial<Plan> = {}): Plan {
  return {
    id: 1,
    code: 'team',
    name: '团队版',
    max_users: 10,
    max_storage_mb: 2048,
    max_expenses_per_month: 500,
    features: {},
    created_at: '2026-09-01T10:00:00+08:00',
    ...overrides,
  };
}

export function makeLicense(overrides: Partial<LicenseRecord> = {}): LicenseRecord {
  return {
    id: 1,
    license_key: 'ABCD****WXYZ',
    is_key_visible: false,
    customer_name: '某某学院',
    max_users: 30,
    valid_until: '2027-12-31',
    status: 'active',
    bound_instance_id: '',
    note: '',
    issued_at: null,
    checked_at: null,
    created_at: '2026-09-01T10:00:00+08:00',
    ...overrides,
  };
}

export function makeExportJob(overrides: Partial<ExportJob> = {}): ExportJob {
  return {
    job: 'job-1',
    slug: 'alpha',
    status: 'running',
    file: '',
    size: 0,
    file_count: 0,
    error: '',
    download_url: '/api/platform/tenants/alpha/export/job-1',
    ...overrides,
  };
}

export function makeLicenseStatus(overrides: Partial<LicenseStatus> = {}): LicenseStatus {
  return {
    state: 'active',
    message: '授权正常。',
    instance_id: 'instance-1',
    valid_until: '2027-01-01T00:00:00+08:00',
    grace_until: null,
    max_users: 5,
    last_checked_at: null,
    last_error: '',
    server_reachable: true,
    ...overrides,
  };
}

export function makeQuota(overrides: Partial<QuotaStatus> = {}): QuotaStatus {
  return {
    enforced: true,
    status: 'active',
    plan: { code: 'team', name: '团队版' },
    usage: {
      users: 3,
      storage_bytes: 1024,
      storage_mb: 1,
      expenses_this_month: 3,
      measured_at: null,
      is_stale: false,
    },
    limits: [
      { key: 'users', label: '成员数量', unit: '人', limit: 10, used: 3, remaining: 7, is_unlimited: false, is_exceeded: false },
      { key: 'storage', label: '存储空间', unit: 'MB', limit: 2048, used: 1, remaining: 2047, is_unlimited: false, is_exceeded: false },
      { key: 'expenses', label: '本月新增记录', unit: '条', limit: 500, used: 3, remaining: 497, is_unlimited: false, is_exceeded: false },
    ],
    expires_on: null,
    expires_in_days: null,
    is_readonly: false,
    readonly_reason: '',
    readonly_message: '',
    ...overrides,
  };
}
