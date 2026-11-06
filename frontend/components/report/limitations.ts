/** 내부 실행 상태는 숨기고, 입점 판단에 필요한 한계만 읽기 쉬운 문장으로 묶는다. */
export function readableLimitations(raw: string): string[] {
  const sentences = raw
    .split(/(?<=[.!?])\s+/u)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  const items = new Set<string>();
  let reviewIncomplete = false;

  for (const sentence of sentences) {
    if (
      /도구 호출|오류 호출|호출·시간|시간 한도|시간 초과|토큰|예산 상한|코드 점수로 마무리|미제출 L 판단|L 판단 미제출|unknown으로 남기고|평가 미완료|피드백 최종 반영|미등록 근거|모델 응답을 완료하지 못해|모델 서비스를 확인하지 못해/.test(
        sentence
      )
    ) {
      reviewIncomplete = true;
      continue;
    }
    if (/(?<![\d,])0건|동종 가게 없음|동종 점포 없음/.test(sentence)) {
      items.add(
        '자료에 점포 수가 0건으로 표시되어도 실제 동종 점포가 없다는 뜻은 아닙니다.'
      );
      continue;
    }
    if (/서울 밖|검색 표본|전수/.test(sentence)) {
      items.add(
        '경쟁 점포 정보는 수집된 검색 표본으로, 실제 점포 전체를 포함하지 않을 수 있습니다.'
      );
      continue;
    }
    if (/건축물 용도|인허가|법적 적합성/.test(sentence)) {
      items.add(
        '건축물 용도와 법적 입점 가능 여부는 이 분석에서 확정하지 않았으니 별도로 확인해야 합니다.'
      );
      continue;
    }
    if (
      /면적 비교|공간 비교|장비 배치|업종별 조건|현장에|현장에서/.test(sentence)
    ) {
      items.add(
        '면적·설비 조건은 추정치이므로 실제 공간과 장비 배치를 현장에서 확인해야 합니다.'
      );
      continue;
    }
    if (
      /수익성|임차인의 지급 능력|임대료|공실 기간|공사비|재무/.test(sentence)
    ) {
      items.add(
        '월세·보증금과 공사비는 분석하지 않으므로 매물 수익성이나 임차인의 지급 능력은 판단할 수 없습니다.'
      );
      continue;
    }
    items.add(sentence);
  }

  if (reviewIncomplete) {
    items.add(
      '일부 업종은 검토가 완료되지 않아 확인된 자료만으로 평가했습니다. 검토 미완료는 부적합 판정이 아닙니다.'
    );
  }
  return [...items];
}
