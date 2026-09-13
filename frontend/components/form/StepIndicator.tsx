import { DM_Mono } from 'next/font/google';
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

const steps: Step[] = [
  { id: 'vacancy-input', number: '1', label: '공실 입력' },
  { id: 'report', number: '2', label: '리포트' },
];

type StepIndicatorProps = {
  currentStep?: number;
};

export default function StepIndicator({ currentStep = 1 }: StepIndicatorProps) {
  return (
    <div className="flex items-center py-4">
      {steps.map((step, index) => {
        const stepNumber = index + 1;
        const active = stepNumber === currentStep;

        return (
          <div key={step.id} className="flex items-center">
            <div className="flex items-center gap-2">
              <div
                className={`${dmMono.className} flex size-[26px] items-center justify-center rounded-full text-[15px] ${
                  active ? '' : 'text-gray-500'
                }`}
                style={{
                  backgroundColor: active
                    ? colors.brand.dark
                    : colors.neutral.border,
                  color: active ? colors.neutral.white : undefined,
                }}
              >
                {step.number}
              </div>
              <p
                className={`text-base ${active ? 'font-medium' : 'font-normal text-gray-500'}`}
                style={active ? { color: colors.brand.dark } : undefined}
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
