import { describe, expect, it } from 'vitest';
import { findEasterEgg } from '@/lib/easterEggs';

describe('findEasterEgg', () => {
  it.each([
    ['경기도 성남시 분당구 판교역로 166', 'pangyo'],
    ['경기도 성남시 분당구 백현동 532', 'pangyo'],
    ['서울 강남구 삼성동 144-28', 'samseong'],
    ['강원 춘천시 강원대학길 1', 'kangwon'],
    ['부산 금정구 부산대학로63번길 2', 'pusan'],
    ['대구광역시 북구 대학로 80 경북대학교', 'kyungpook'],
    ['전남광주통합특별시 북구 용봉로 77', 'chonnam'],
    ['대전광역시 유성구 대학로 99', 'chungnam'],
  ])('%s 는 %s 로 맞는다', (address, id) => {
    expect(findEasterEgg(address)?.id).toBe(id);
  });

  it.each([
    ['서울 강남구 삼성동 144-28 1층', 'samseong'],
    ['판교역로 166 3층', 'pangyo'],
    ['경기 성남시 분당구 판교역로 １６６', 'pangyo'],
    ['삼성동 144–28', 'samseong'],
    ['백현동 532번지', 'pangyo'],
  ])('%s 는 %s 로 맞는다 (층·전각·긴 줄표)', (address, id) => {
    expect(findEasterEgg(address)?.id).toBe(id);
  });

  it('띄어쓰기가 달라도 맞는다', () => {
    expect(findEasterEgg('판교역로166')?.id).toBe('pangyo');
    expect(findEasterEgg('서울특별시 강남구 삼성동144-28')?.id).toBe(
      'samseong'
    );
  });

  it.each([
    '서울 종로구 대학로 80',
    '판교역로 1660',
    '판교역로 166-1',
    '삼성동 144-280',
    '백현동 5321',
    '서울 강남구 테헤란로 152',
    '판교역로 166번길 10',
    '용봉로 77번길 5',
    '대전 유성구 대학로 99번길 3',
    '강원대학길 1번길',
    '대구 북구 대학로 80번길 2',
    '',
  ])('%s 는 맞지 않는다', (address) => {
    expect(findEasterEgg(address)).toBeNull();
  });

  it('학교 링크는 원문 주소를 쓴다', () => {
    expect(findEasterEgg('부산대학로63번길 2')?.links).toEqual([
      {
        label: '부산 바캉스 MV 보기',
        href: 'https://www.youtube.com/watch?v=PehlE8g0ReA',
      },
    ]);
    expect(findEasterEgg('용봉로 77')?.links).toEqual(
      findEasterEgg('대구 북구 대학로 80')?.links
    );
    expect(findEasterEgg('대전 유성구 대학로 99')?.links[0].href).toBe(
      'https://www.sungsimdang.co.kr'
    );
  });
});
