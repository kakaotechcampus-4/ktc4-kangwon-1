import { describe, expect, it } from 'vitest';
import { readableLimitations } from './limitations';

const INCOMPLETE =
  'AI 검토가 모두 끝나지는 않았습니다. 끝나지 않은 부분은 확인된 자료만으로 평가했습니다. 검토 미완료는 부적합 판정이 아닙니다.';

const EXCLUDED = '근거를 확인할 수 없는 인용 부분은 리포트에서 뺐습니다.';
const ZERO_NOTE =
  '자료에 점포 수가 0건으로 표시되어도 실제 동종 점포가 없다는 뜻은 아닙니다.';

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
        'L 판단 미제출 업종 수: 12. 호출·시간·토큰 예산 상한에 도달해 코드 점수로 마무리했습니다. 피드백 최종 반영을 완료하지 못했습니다.'
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

  it('점포가 0건인 문장은 그대로 두고 보충 안내를 덧붙인다', () => {
    expect(readableLimitations('반경 안 동종 점포가 0건입니다.')).toEqual([
      '반경 안 동종 점포가 0건입니다.',
      ZERO_NOTE,
    ]);
  });

  it.each([
    '이 건물은 1층 일반음식점 허가 이력이 있으나 인허가 변경 여부는 확인하지 못했습니다.',
    '출입구 경사로 폭은 현장에서 재 봐야 합니다.',
    '임대료 수준은 자료가 없어 비교하지 않았습니다.',
  ])('인허가·현장·임대료 문장은 모델 문장 그대로 둔다', (sentence) => {
    expect(readableLimitations(sentence)).toEqual([sentence]);
  });

  it('0건 문장이 둘이어도 보충 안내는 한 번만 붙인다', () => {
    expect(
      readableLimitations(
        '반경 300m 안 동종 점포 0건입니다. 인근 동종 점포 0건이라 경쟁은 낮아 보입니다.'
      )
    ).toEqual([
      '반경 300m 안 동종 점포 0건입니다.',
      ZERO_NOTE,
      '인근 동종 점포 0건이라 경쟁은 낮아 보입니다.',
    ]);
  });

  it('검색 표본 문장은 그대로 두고 보충 안내를 덧붙인다', () => {
    expect(readableLimitations('서울 밖 점포는 검색 표본에 없습니다.')).toEqual(
      [
        '서울 밖 점포는 검색 표본에 없습니다.',
        '경쟁 점포 정보는 수집된 검색 표본으로, 실제 점포 전체를 포함하지 않을 수 있습니다.',
      ]
    );
  });

  it.each([
    '미등록 근거를 인용한 부분을 제외했습니다.',
    '미등록 근거를 인용한 문장을 제외했습니다.',
  ])('미등록 근거 문장은 숨기고 근거 제외 안내만 붙인다', (sentence) => {
    expect(readableLimitations(sentence)).toEqual([EXCLUDED]);
  });

  it('AI가 업종 전부를 검토하지 못한 경우에도 일부 업종이라고 하지 않는다', () => {
    const [note] = readableLimitations(
      'L 판단 미제출 업종 수: 51. 모델 응답을 완료하지 못해 코드 점수로 마무리했습니다.'
    );
    expect(note).toBe(INCOMPLETE);
    expect(note).not.toContain('일부 업종');
  });

  it('근거 제외 안내 뒤에 검토 미완료 안내를 붙인다', () => {
    expect(
      readableLimitations(
        '토큰 한도에 걸렸습니다. 미등록 근거를 인용한 문장을 제외했습니다.'
      )
    ).toEqual([EXCLUDED, INCOMPLETE]);
  });

  it('공백만 다른 같은 문장은 한 번만 보여 준다', () => {
    expect(
      readableLimitations(
        '주차 정보는 반영하지 않았습니다.  주차   정보는 반영하지 않았습니다.'
      )
    ).toEqual(['주차 정보는 반영하지 않았습니다.']);
  });
});
