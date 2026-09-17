import { Input, SegmentedControl } from '@mantine/core';
import type { UserRole } from '../../../api/types';
import { ROLE_OPTIONS } from '../../../lib/users';

interface RoleControlProps {
  value: UserRole;
  onChange: (role: UserRole) => void;
  /** 当前登录的管理员编辑自己：不能降级 */
  isDemoteLocked?: boolean;
}

const ROLE_HINT = '管理员可管理用户、系统设置、分类、凭证清单规则与备份';
const DEMOTE_LOCKED_HINT = '不能把自己改为普通用户';

export function RoleControl({ value, onChange, isDemoteLocked = false }: RoleControlProps) {
  const data = ROLE_OPTIONS.map((option) => ({ ...option, disabled: isDemoteLocked && option.value === 'member' }));
  return (
    <Input.Wrapper label="角色" description={isDemoteLocked ? DEMOTE_LOCKED_HINT : ROLE_HINT}>
      <div>
        <SegmentedControl
          mt={4}
          size="xs"
          data={data}
          value={value}
          onChange={(next) => onChange(next === 'admin' ? 'admin' : 'member')}
        />
      </div>
    </Input.Wrapper>
  );
}
