import { DM_Mono } from 'next/font/google';
import { Check } from 'lucide-react';
import { colors } from '@/styles/tokens';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['500'],
});

type Step = {
  id: string;
  number: string;
  label: string;
};

// 공실 입력 → 분석 진행 → 리포트, 전체 3단계 흐름.
const steps: Step[] = [
  { id: 'vacancy-input', number: '1', label: '공실 입력' },
  { id: 'analysis-progress', number: '2', label: '분석 진행' },
  { id: 'report', number: '3', label: '리포트' },
];

type StepIndicatorProps = {
  currentStep?: number;
};

export default function StepIndicator({ currentStep = 1 }: StepIndicatorProps) {
  return (
    <div className="flex items-center py-4">
      {steps.map((step, index) => {
        const stepNumber = index + 1;
        const isDone = stepNumber < currentStep;
        const isActive = stepNumber === currentStep;
        const isEmphasized = isDone || isActive;

        return (
          <div key={step.id} className="flex items-center">
            <div className="flex items-center gap-2">
              <div
                className={`${dmMono.className} flex size-[26px] items-center justify-center rounded-full text-[15px] ${
                  isEmphasized ? '' : 'text-gray-500'
                }`}
                style={{
                  backgroundColor: isEmphasized
                    ? colors.brand.dark
                    : colors.neutral.border,
                  color: isEmphasized ? colors.neutral.white : undefined,
                }}
              >
                {isDone ? <Check size={14} strokeWidth={2.5} /> : step.number}
              </div>
              <p
                className={`text-base ${isEmphasized ? 'font-medium' : 'font-normal text-gray-500'}`}
                style={
                  isEmphasized
                    ? {
                        color: isActive
                          ? colors.brand.dark
                          : colors.neutral.black,
                      }
                    : undefined
                }
              >
                {step.label}
              </p>
            </div>

            {index < steps.length - 1 && (
              <div
                className="mx-3.5 h-px w-10"
                style={{ backgroundColor: colors.neutral.border }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
