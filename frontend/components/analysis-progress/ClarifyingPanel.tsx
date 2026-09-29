'use client';

import { useState } from 'react';
import { DM_Mono } from 'next/font/google';
import { Bot, Send } from 'lucide-react';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import { colors } from '@/styles/tokens';
import type { ClarifyingQuestion } from '@/lib/mockData/analysisProgress';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

type ClarifyingChatProps = {
  questions: ClarifyingQuestion[];
  onSubmit: (answers: Record<string, string>, freeText: string) => void;
};

export default function ClarifyingChat({
  questions,
  onSubmit,
}: ClarifyingChatProps) {
  // 답변/입력값은 로컬 state로만 관리한다 — 실제 제출 API는 아직 없다.
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [freeText, setFreeText] = useState('');

  function handleSelect(questionId: string, option: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: option }));
  }

  function handleSubmit() {
    // mock 처리 — 실제 API 연동 없이 콘솔에만 기록한다.
    console.log('[ClarifyingChat] 답변 제출(mock):', { answers, freeText });
    onSubmit(answers, freeText);
  }

  return (
    <div className="flex w-full flex-col gap-4">
      <div
        className="flex items-start gap-3 rounded-xl p-5"
        style={{ backgroundColor: `${colors.brand.primary}14` }}
      >
        <BotAvatar size={36} iconSize={18} />
        <div className="flex flex-col gap-0.5">
          <p className="font-semibold" style={{ color: colors.neutral.black }}>
            추가로 확인이 필요한 내용이 있어요
          </p>
          <p className="text-sm" style={{ color: 'var(--color-gray-500)' }}>
            더 정확한 분석을 위해 몇 가지를 여쭤볼게요.
          </p>
        </div>
      </div>

      {questions.map((question) => (
        <QuestionCard
          key={question.questionId}
          question={question}
          selected={answers[question.questionId]}
          onSelect={(option) => handleSelect(question.questionId, option)}
        />
      ))}

      <div
        className="flex items-center gap-3 rounded-xl border p-3.5"
        style={{
          borderColor: colors.neutral.border,
          backgroundColor: colors.neutral.white,
        }}
      >
        <Input
          value={freeText}
          onChange={(event) => setFreeText(event.target.value)}
          placeholder="추가로 전달하고 싶은 내용이 있다면 입력해주세요."
          className="flex-1"
          style={{ border: 'none', padding: 0, backgroundColor: 'transparent' }}
        />
        <button
          type="button"
          onClick={handleSubmit}
          className="flex size-9 shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: colors.neutral.background }}
        >
          <Send size={16} style={{ color: 'var(--color-gray-400)' }} />
        </button>
      </div>

      <Button
        type="button"
        variant="primary"
        className="w-full justify-center"
        style={{ padding: '14px 24px' }}
        onClick={handleSubmit}
      >
        답변하고 분석 계속하기 →
      </Button>
    </div>
  );
}

function BotAvatar({ size, iconSize }: { size: number; iconSize: number }) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full"
      style={{
        width: size,
        height: size,
        backgroundColor: colors.neutral.white,
        border: `1.5px solid ${colors.brand.primary}`,
      }}
    >
      <Bot size={iconSize} style={{ color: colors.brand.primary }} />
    </div>
  );
}

function QuestionCard({
  question,
  selected,
  onSelect,
}: {
  question: ClarifyingQuestion;
  selected?: string;
  onSelect: (option: string) => void;
}) {
  return (
    <div
      className="flex flex-col gap-4 rounded-xl border p-5"
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    >
      <div className="flex items-start gap-2.5">
        <BotAvatar size={28} iconSize={14} />
        <div className="flex flex-1 flex-col gap-1">
          <p
            className="text-[15px] font-semibold"
            style={{ color: colors.neutral.black }}
          >
            {question.question}
          </p>
          <p className="text-[13px]" style={{ color: 'var(--color-gray-500)' }}>
            {question.context}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {question.options.map((option) => {
          const isSelected = selected === option;
          return (
            <button
              key={option}
              type="button"
              onClick={() => onSelect(option)}
              className="rounded-lg border px-4 py-2.5 text-sm"
              style={{
                borderColor: isSelected
                  ? colors.brand.dark
                  : colors.neutral.border,
                backgroundColor: isSelected
                  ? `${colors.brand.primary}14`
                  : colors.neutral.white,
                color: isSelected ? colors.brand.dark : 'var(--color-gray-500)',
                fontWeight: isSelected ? 600 : 500,
              }}
            >
              {option}
            </button>
          );
        })}
      </div>

      <p
        className={`${dmMono.className} text-right text-xs`}
        style={{ color: 'var(--color-gray-400)' }}
      >
        {question.askedAt}
      </p>
    </div>
  );
}
