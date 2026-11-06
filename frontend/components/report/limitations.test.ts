import { describe, expect, it } from 'vitest';
import { readableLimitations } from './limitations';

const INCOMPLETE =
  '일부 업종은 검토가 완료되지 않아 확인된 자료만으로 평가했습니다. 검토 미완료는 부적합 판정이 아닙니다.';

describe('분석의 한계 문장', () => {
  it('띄어쓰기로 이어진 문장을 하나씩 나눠 그대로 보여 준다', () => {
    expect(
      readableLimitations(
        '유동인구는 시간대별 추정치입니다. 주말 자료는 한 해치만 있습니다. 동종 점포는 120건으로 집계했습니다.'
      )
    ).toEqual([
      '유동인구는 시간대별 추정치입니다.',
      '주말 자료는 한 해치만 있습니다.',
      '동종 점포는 120건으로 집계했습니다.',
    ]);
  });

  it('서버가 붙인 내부 진행 문장은 검토 미완료 안내 하나로 묶는다', () => {
    expect(
      readableLimitations(
        'L 판단 미제출 업종 수: 12. 호출·시간·토큰 예산 상한에 도달해 코드 점수로 마무리했습니다. 피드백 최종 반영을 완료하지 못했습니다. 미등록 근거를 인용한 문장을 제외했습니다.'
      )
    ).toEqual([INCOMPLETE]);
  });

  it('모델 문장은 남기고 평가 미완료는 안내로 바꾼다', () => {
    expect(
      readableLimitations(
        '주차 정보는 반영하지 않았습니다. 평가 미완료: 실패한 평가를 동의로 간주하지 않습니다.'
      )
    ).toEqual(['주차 정보는 반영하지 않았습니다.', INCOMPLETE]);
  });

  it('점포가 0건인 문장만 0건 안내로 바꾼다', () => {
    expect(readableLimitations('반경 안 동종 점포가 0건입니다.')).toEqual([
      '자료에 점포 수가 0건으로 표시되어도 실제 동종 점포가 없다는 뜻은 아닙니다.',
    ]);
  });
});
