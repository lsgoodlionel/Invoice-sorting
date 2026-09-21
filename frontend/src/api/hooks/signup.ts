import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type {
  ReferralCheck,
  RegisterCodeInfo,
  RegisterInput,
  SignupApplicationInput,
  SignupApplicationReceipt,
} from '../signupTypes';
import type { AuthResult } from '../types';
import { useRefreshAuthStatus } from './auth';
import { queryKeys } from './keys';

// 公开接口（无需登录，仅多账套部署）：申请、推荐码校验、注册码校验与完成注册。

export const signupApi = {
  apply: (input: SignupApplicationInput) => api.post<SignupApplicationReceipt>('/signup/applications', input),
  checkReferral: (code: string) => api.get<ReferralCheck>(`/signup/referral/${encodeURIComponent(code)}`),
  checkRegisterCode: (code: string) => api.get<RegisterCodeInfo>('/signup/register', { code }),
  register: (input: RegisterInput) => api.post<AuthResult>('/signup/register', input),
};

/** 提交申请；错误（限流 429、邮箱已有待审批申请 409）由表单内联展示原文。 */
export const useSubmitApplication = () => useMutation({ mutationFn: signupApi.apply, meta: { silent: true } });

/** 校验推荐码；无效时页面自行提示，不弹全局错误。 */
export const useReferralCheck = (code: string) =>
  useQuery({
    queryKey: queryKeys.signupReferral(code),
    queryFn: () => signupApi.checkReferral(code),
    enabled: Boolean(code),
    retry: false,
    staleTime: Infinity,
    meta: { silent: true },
  });

/** 校验注册码：有效返回绑定邮箱；无效、过期、已使用返回 4xx 与中文说明。 */
export const useRegisterCode = (code: string) =>
  useQuery({
    queryKey: queryKeys.signupRegister(code),
    queryFn: () => signupApi.checkRegisterCode(code),
    enabled: Boolean(code),
    retry: false,
    staleTime: Infinity,
    meta: { silent: true },
  });

/** 完成注册：后端建号、开通账套并登录；成功后刷新认证状态直接进入应用。 */
export function useRegister() {
  const refresh = useRefreshAuthStatus();
  return useMutation({ mutationFn: signupApi.register, onSuccess: refresh, meta: { silent: true } });
}
