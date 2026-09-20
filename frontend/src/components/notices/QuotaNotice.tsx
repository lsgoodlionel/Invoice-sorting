import { useQuotaStatus } from '../../api/hooks/quota';
import { quotaNotice } from '../../lib/platform';
import { NoticeBar } from './NoticeBar';

/**
 * 套餐额度提示条：只读或已达上限红条、即将到期黄条。
 * 单账套部署（enforced=false）与接口不可用时都不显示，不打扰用户。
 */
export function QuotaNotice() {
  const { data } = useQuotaStatus();
  const notice = quotaNotice(data);
  if (!notice) return null;
  return <NoticeBar tone={notice.tone} message={notice.message} label="额度提示" />;
}
