import { useSearchParams } from 'react-router';
import { errorMessage } from '../../api/client';
import { useRegisterCode } from '../../api/hooks/signup';
import { AuthLoading } from '../../components/auth/AuthLayout';
import { RegisterForm } from '../../components/signup/RegisterForm';
import { RegisterUnavailable } from '../../components/signup/RegisterUnavailable';

const MISSING_CODE = '链接里缺少注册码，请从审批通过的邮件中重新打开注册链接。';

/** 公开的注册页 /register?code=：先校验注册码，再设置用户名与密码。 */
export function RegisterPage() {
  const [params] = useSearchParams();
  const code = (params.get('code') ?? '').trim();
  const check = useRegisterCode(code);

  if (!code) return <RegisterUnavailable message={MISSING_CODE} />;
  if (check.isLoading) return <AuthLoading />;
  if (!check.data) return <RegisterUnavailable message={errorMessage(check.error)} />;
  return <RegisterForm code={code} info={check.data} />;
}
