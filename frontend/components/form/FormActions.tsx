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
    <div className="flex w-full justify-end gap-3">
      <Button
        type="button"
        variant="outline"
        className="text-gray-500"
        style={{ padding: '14px 24px' }}
      >
        임시 저장
      </Button>
      <Button
        type="button"
        variant="primary"
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
