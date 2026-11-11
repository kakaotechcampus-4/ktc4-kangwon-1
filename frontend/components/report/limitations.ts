const INTERNAL_STATUS =
  /도구 호출|오류 호출|호출·시간|시간 한도|시간 초과|토큰|예산 상한|코드 점수로 마무리|미제출 L 판단|L 판단 미제출|unknown으로 남기고|평가 미완료|피드백 최종 반영|모델 응답을 완료하지 못해|모델 서비스를 확인하지 못해/;
const UNREGISTERED_EVIDENCE = /미등록 근거/;
const ZERO_STORES = /(?<![\d,])0건|동종 가게 없음|동종 점포 없음/;
const SAMPLE_ONLY = /서울 밖|검색 표본|전수/;

const ZERO_STORES_NOTE =
  '자료에 점포 수가 0건으로 표시되어도 실제 동종 점포가 없다는 뜻은 아닙니다.';
const SAMPLE_ONLY_NOTE =
  '경쟁 점포 정보는 수집된 검색 표본으로, 실제 점포 전체를 포함하지 않을 수 있습니다.';
const EXCLUDED_EVIDENCE_NOTE =
  '근거를 확인할 수 없는 인용 부분은 리포트에서 뺐습니다.';
const REVIEW_INCOMPLETE_NOTE =
  'AI 검토가 모두 끝나지는 않았습니다. 끝나지 않은 부분은 확인된 자료만으로 평가했습니다. 검토 미완료는 부적합 판정이 아닙니다.';

/** 내부 실행 상태는 숨기고, 모델이 쓴 한계 문장은 그대로 두며 오해하기 쉬운 경우에만 짧은 보충 안내를 덧붙인다. */
export function readableLimitations(raw: string): string[] {
  const sentences = raw
    .split(/(?<=[.!?])\s+/u)
    .map((sentence) => sentence.trim().replace(/\s+/gu, ' '))
    .filter(Boolean);
  const items = new Set<string>();
  let reviewIncomplete = false;
  let evidenceExcluded = false;

  for (const sentence of sentences) {
    if (UNREGISTERED_EVIDENCE.test(sentence)) {
      evidenceExcluded = true;
      continue;
    }
    if (INTERNAL_STATUS.test(sentence)) {
      reviewIncomplete = true;
      continue;
    }
    items.add(sentence);
    if (ZERO_STORES.test(sentence)) {
      items.add(ZERO_STORES_NOTE);
    }
    if (SAMPLE_ONLY.test(sentence)) {
      items.add(SAMPLE_ONLY_NOTE);
    }
  }

  if (evidenceExcluded) {
    items.add(EXCLUDED_EVIDENCE_NOTE);
  }
  if (reviewIncomplete) {
    items.add(REVIEW_INCOMPLETE_NOTE);
  }
  return [...items];
}
