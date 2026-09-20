import { useLicenseStatus } from '../../api/hooks/license';
import { NoticeBar } from './NoticeBar';

/**
 * 私有化授权提示条：宽限期黄条、只读红条，其余状态不显示。
 * 文案直接用后端的 message，避免前后端口径不一致。
 */
export function LicenseNotice() {
  const { data } = useLicenseStatus();
  if (!data) return null;
  if (data.state === 'grace') return <NoticeBar tone="warning" message={data.message} label="授权提示" />;
  if (data.state === 'readonly') return <NoticeBar tone="danger" message={data.message} label="授权提示" />;
  return null;
}
