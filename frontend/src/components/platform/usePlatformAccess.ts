import { useAuthStatus } from '../../api/hooks/auth';
import { usePlatformOverview } from '../../api/hooks/platform';
import { useCurrentUser } from '../auth/CurrentUserContext';

/**
 * 是否显示平台运营入口。
 *
 * 只在多账套部署、且当前账号是管理员时才去探测 `/api/platform/overview`：
 * 探测成功才是平台管理员（普通租户管理员会得到 403，入口保持隐藏）。
 * 单账套私有化部署永远返回 false——界面不出现账套与平台概念。
 */
export function usePlatformAccess(): { canSeePlatform: boolean; isChecking: boolean } {
  const { data: status } = useAuthStatus();
  const { isAdmin } = useCurrentUser();
  const isCandidate = Boolean(status?.multi_tenant) && isAdmin;
  const { data, isLoading } = usePlatformOverview(isCandidate);
  return { canSeePlatform: isCandidate && Boolean(data), isChecking: isCandidate && isLoading };
}
