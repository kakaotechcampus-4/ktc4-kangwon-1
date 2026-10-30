import Button from '@/components/ui/Button';

type FormActionsProps = {
  isAnalyzing: boolean;
  onSubmit: () => void;
};

export default function FormActions({
  isAnalyzing,
  onSubmit,
}: FormActionsProps) {
  return (
    <div className="flex w-full flex-col-reverse gap-3 sm:flex-row sm:justify-end">
      <Button
        type="button"
        variant="outline"
        className="min-h-12 w-full text-gray-500 sm:w-auto"
        style={{ padding: '14px 24px' }}
      >
        임시 저장
      </Button>
      <Button
        type="button"
        variant="primary"
        className="min-h-12 w-full whitespace-normal text-center leading-snug sm:w-auto"
        style={{ padding: '14px 24px' }}
        disabled={isAnalyzing}
        onClick={onSubmit}
      >
        {isAnalyzing
          ? '분석 중... (최대 10분 정도 걸릴 수 있어요)'
          : '다음 · AI 판독 결과 확인'}
      </Button>
    </div>
  );
}
