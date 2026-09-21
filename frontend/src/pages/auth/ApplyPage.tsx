import { Anchor, Button, Text } from '@mantine/core';
import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { errorMessage } from '../../api/client';
import { useReferralCheck, useSubmitApplication } from '../../api/hooks/signup';
import { AuthLayout, AuthLoading } from '../../components/auth/AuthLayout';
import { ApplyFormFields } from '../../components/signup/ApplyFormFields';
import { ApplyReceipt } from '../../components/signup/ApplyReceipt';
import { ReferralNotice } from '../../components/signup/ReferralNotice';
import { EMPTY_APPLY_FORM, isApplyFormComplete, toApplicationPayload, type ApplyForm } from '../../lib/signup';

const INTRO = '填写你的基本情况与使用需求，平台审核通过后会把注册链接发到你的邮箱。';

/** 公开的申请页 /apply；带 ?ref=推荐码 时先校验并显示推荐人。 */
export function ApplyPage() {
  const [params] = useSearchParams();
  const refCode = (params.get('ref') ?? '').trim();
  const referral = useReferralCheck(refCode);
  const submit = useSubmitApplication();
  const [form, setForm] = useState<ApplyForm>(EMPTY_APPLY_FORM);
  const canSubmit = isApplyFormComplete(form);

  const patch = (next: Partial<ApplyForm>) => {
    setForm((current) => ({ ...current, ...next }));
    if (submit.error) submit.reset();
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit || submit.isPending) return;
    submit.mutate(toApplicationPayload(form, referral.data ? refCode : null));
  };

  if (submit.data) return <ApplyReceipt receipt={submit.data} email={form.email.trim()} />;
  if (refCode && referral.isLoading) return <AuthLoading />;

  const footer = <Anchor component={Link} to="/" size="xs">已有账号？直接登录</Anchor>;
  return (
    <AuthLayout title="申请使用" subtitle={INTRO} footer={footer}>
      <ReferralNotice referrerName={referral.data?.referrer_name ?? null} isInvalid={referral.isError} />
      <form onSubmit={onSubmit} noValidate>
        <ApplyFormFields form={form} onChange={patch} />
        {submit.error && <Text size="sm" c="red.7" role="alert" mt="sm">{errorMessage(submit.error)}</Text>}
        <Button type="submit" variant="filled" fullWidth size="md" mt="xl" loading={submit.isPending} disabled={!canSubmit}>
          提交申请
        </Button>
      </form>
    </AuthLayout>
  );
}
