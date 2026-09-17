import { Group, Text, Tooltip, UnstyledButton } from '@mantine/core';
import type { ExpenseStatus } from '../api/types';
import { STATUS_ORDER, statusRank, stepLabel } from '../lib/status';

interface StatusStepperProps {
  status: ExpenseStatus;
  onStepClick?: (status: ExpenseStatus) => void;
  /** 免发票记录：第二步显示“已收凭证” */
  invoiceExempt?: boolean;
}

/** 五步主状态线；作废时整体置灰并加删除线。 */
export function StatusStepper({ status, onStepClick, invoiceExempt = false }: StatusStepperProps) {
  const rank = statusRank(status);
  const isVoid = status === 'void';
  return (
    <Group gap={0} wrap="nowrap" className="stepper" data-void={isVoid || undefined} role="list" aria-label="状态进度">
      {STATUS_ORDER.map((step, index) => {
        const label = stepLabel(step, invoiceExempt);
        const state = isVoid ? 'void' : index < rank ? 'done' : index === rank ? 'current' : 'todo';
        return (
          <Tooltip key={step} label={onStepClick ? `手动设为「${label}」` : label}>
            <UnstyledButton
              role="listitem"
              className="stepper-step"
              data-state={state}
              aria-current={state === 'current' ? 'step' : undefined}
              disabled={!onStepClick}
              onClick={() => onStepClick?.(step)}
            >
              <span className="stepper-dot" aria-hidden />
              <Text size="xs" fw={state === 'current' ? 700 : 400}>
                {label}
              </Text>
            </UnstyledButton>
          </Tooltip>
        );
      })}
    </Group>
  );
}
