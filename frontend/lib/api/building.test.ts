import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ADDRESS_ERROR_NOTE,
  LOOKUP_ERROR_NOTE,
  fetchBuildingInfo,
  normalizeFloor,
  toBuildingInfo,
  type BuildingRegistryResponse,
  type LookupId,
  type LookupStatus,
} from './building';

afterEach(() => vi.unstubAllGlobals());

const TITLE = {
  dong_name: null,
  building_name: '성희프라자',
  main_use: '제2종근린생활시설',
  ground_floors: 7,
  underground_floors: 2,
  total_area_m2: 12301.78,
  parking_spaces: 82,
};

const REGISTRY: BuildingRegistryResponse = {
  road_address: '서울 송파구 위례광장로 199',
  jibun_address: '서울 송파구 장지동 880-1',
  titles: [TITLE],
  floors: [
    {
      dong_name: null,
      floor: '지하 1층',
      use: '기타제2종근린생활시설',
      use_detail: '지하주차장',
      area_m2: 1925.34,
    },
    {
      dong_name: null,
      floor: '4층',
      use: '일반음식점',
      use_detail: '제2종근린생활시설',
      area_m2: 275.49,
    },
    {
      dong_name: null,
      floor: '4층',
      use: '의원',
      use_detail: '제1종근린생활시설',
      area_m2: 498.12,
    },
    {
      dong_name: null,
      floor: '4층',
      use: '일반음식점',
      use_detail: '제2종근린생활시설',
      area_m2: 100,
    },
    {
      dong_name: 'B동',
      floor: '4층',
      use: '사무소',
      use_detail: '업무시설',
      area_m2: 220.8,
    },
  ],
  units: [
    {
      dong_name: null,
      unit_name: '401호',
      floor: '4층',
      use: '학원',
      use_detail: '교육연구시설',
      area_m2: 100.8,
    },
    {
      dong_name: null,
      unit_name: '404호',
      floor: '4층',
      use: '의원',
      use_detail: '제1종근린생활시설',
      area_m2: 93.6,
    },
    {
      dong_name: null,
      unit_name: 'B101호',
      floor: '지하 1층',
      use: '창고',
      use_detail: null,
      area_m2: 50,
    },
  ],
  sewage: [
    { method: null, method_name: '접촉폭기방법' },
    { method: '정화조', method_name: '부패탱크방법' },
  ],
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('건축물대장 응답을 화면 칸으로 옮기기', () => {
  it('표제부 값과 층수 문구를 채운다', () => {
    const info = toBuildingInfo(REGISTRY, '입력 주소', '4층 404호');
    expect(info.buildingName).toBe('성희프라자');
    expect(info.address).toBe('서울 송파구 위례광장로 199');
    expect(info.floorLabel).toBe('4층');
    expect(info.sourceNote).toBeUndefined();
    expect(info.mainUse).toEqual({
      value: '제2종근린생활시설',
      registryValue: '제2종근린생활시설',
      source: 'registry',
    });
    expect(info.totalAreaM2.value).toBe(12301.78);
    expect(info.floors.value).toBe('지상 7층 · 지하 2층');
    expect(info.facility.value).toBe('type2');
    expect(info.parking.value).toBe('possible');
    expect(info.sewage.value).toBe('정화조');
  });

  it('같은 층·같은 동의 용도를 겹치지 않게 잇는다', () => {
    expect(toBuildingInfo(REGISTRY, '', '4층').floorUse.value).toBe(
      '일반음식점 · 의원'
    );
  });

  it('호수가 있으면 그 호실의 전용면적을 쓴다', () => {
    expect(
      toBuildingInfo(REGISTRY, '', '4층 404호').exclusiveAreaM2.value
    ).toBe(93.6);
  });

  it('호수가 없고 그 층 호실이 여럿이면 비워 둔다', () => {
    const info = toBuildingInfo(REGISTRY, '', '4층');
    expect(info.exclusiveAreaM2).toEqual({
      value: null,
      registryValue: null,
      source: 'missing',
    });
  });

  it('호수가 없고 그 층 호실이 하나면 그 면적을 쓴다', () => {
    expect(toBuildingInfo(REGISTRY, '', '지하1층').exclusiveAreaM2.value).toBe(
      50
    );
  });

  it('없는 호수는 다른 호실로 대신하지 않는다', () => {
    expect(
      toBuildingInfo(REGISTRY, '', '지하 1층 B102호').exclusiveAreaM2.value
    ).toBeNull();
  });

  it('지하가 없으면 지상 층수만 쓴다', () => {
    const registry = {
      ...REGISTRY,
      titles: [{ ...TITLE, underground_floors: 0 }],
    };
    expect(toBuildingInfo(registry, '', '4층').floors.value).toBe('지상 7층');
  });

  it.each([0, null])('주차 %s대는 사용자가 고르게 비워 둔다', (spaces) => {
    const registry = {
      ...REGISTRY,
      titles: [{ ...TITLE, parking_spaces: spaces }],
    };
    expect(toBuildingInfo(registry, '', '4층').parking.source).toBe('missing');
  });

  it('표제부가 실패하면 동으로 거르지 않는다', () => {
    const info = toBuildingInfo(
      { ...REGISTRY, titles: null },
      '입력 주소',
      '4층'
    );
    expect(info.floorUse.value).toBe('일반음식점 · 의원 · 사무소');
    expect(info.mainUse.source).toBe('missing');
    expect(info.facility.source).toBe('missing');
    expect(info.buildingName).toBe('');
  });

  it('입력 층을 못 읽으면 층 용도와 면적을 비워 둔다', () => {
    const info = toBuildingInfo(REGISTRY, '', '1F');
    expect(info.floorLabel).toBe('해당 층');
    expect(info.floorUse.value).toBeNull();
    expect(info.exclusiveAreaM2.value).toBeNull();
  });
});

describe('층 표기 맞추기', () => {
  it.each([
    ['4층 401호', '4층'],
    ['지하1층', '지하 1층'],
    ['지하 1 층', '지하 1층'],
    ['12 층', '12층'],
    ['B1층', '지하 1층'],
    ['1층 B101호', '1층'],
    ['401호', null],
    ['0층', null],
    ['1F', null],
    ['', null],
    ['지1층', '지하 1층'],
    ['지1층 B01호', '지하 1층'],
    ['-1층', null],
    ['1.5층', null],
    ['중1층', null],
    ['M1층', null],
    ['상가동 1층 101호', '1층'],
    ['상가동1층', '1층'],
    ['B동 3층', '3층'],
  ])('%s → %s', (input, expected) => {
    expect(normalizeFloor(input)).toBe(expected);
  });
});

const MULTI_DONG: BuildingRegistryResponse = {
  road_address: null,
  jibun_address: null,
  titles: [
    {
      dong_name: '101동',
      building_name: '래미안',
      main_use: '공동주택',
      ground_floors: 15,
      underground_floors: 2,
      total_area_m2: 12000,
      parking_spaces: 200,
    },
    {
      dong_name: '상가동',
      building_name: '래미안 상가',
      main_use: '제1종근린생활시설',
      ground_floors: 2,
      underground_floors: 0,
      total_area_m2: 900,
      parking_spaces: 10,
    },
  ],
  floors: [
    {
      dong_name: '101동',
      floor: '1층',
      use: '공동주택',
      use_detail: null,
      area_m2: 500,
    },
    {
      dong_name: '상가동',
      floor: '1층',
      use: '소매점',
      use_detail: null,
      area_m2: 300,
    },
  ],
  units: [
    {
      dong_name: '101동',
      unit_name: '101호',
      floor: '1층',
      use: '공동주택',
      use_detail: null,
      area_m2: 84.97,
    },
    {
      dong_name: '상가동',
      unit_name: '101호',
      floor: '1층',
      use: '소매점',
      use_detail: null,
      area_m2: 45.2,
    },
  ],
  sewage: null,
};

describe('입력의 동 이름으로 표제부 고르기', () => {
  it('입력에 맞는 동의 표제부와 그 동의 행을 쓴다', () => {
    const info = toBuildingInfo(MULTI_DONG, '', '상가동 1층 101호');
    expect(info.buildingName).toBe('래미안 상가');
    expect(info.mainUse.value).toBe('제1종근린생활시설');
    expect(info.facility.value).toBe('type1');
    expect(info.floorUse.value).toBe('소매점');
    expect(info.exclusiveAreaM2.value).toBe(45.2);
    expect(info.floors.value).toBe('지상 2층');
  });

  it('동이 여럿인데 입력에 동이 없으면 층 용도와 면적을 비운다', () => {
    const info = toBuildingInfo(MULTI_DONG, '', '1층 101호');
    expect(info.floorUse.value).toBeNull();
    expect(info.exclusiveAreaM2.value).toBeNull();
    expect(info.mainUse.value).toBe('공동주택');
  });

  it('맞는 동이 없으면 층 용도와 면적을 비운다', () => {
    const info = toBuildingInfo(MULTI_DONG, '', 'C동 1층 101호');
    expect(info.floorUse.value).toBeNull();
    expect(info.exclusiveAreaM2.value).toBeNull();
  });

  it('동이 하나뿐이면 입력에 동이 없어도 그 동의 행을 쓴다', () => {
    const registry: BuildingRegistryResponse = {
      ...REGISTRY,
      titles: [{ ...TITLE, dong_name: 'A동' }],
      floors: [
        {
          dong_name: 'A동',
          floor: '4층',
          use: '사무소',
          use_detail: null,
          area_m2: 10,
        },
        {
          dong_name: 'B동',
          floor: '4층',
          use: '창고',
          use_detail: null,
          area_m2: 10,
        },
      ],
    };
    expect(toBuildingInfo(registry, '', '4층').floorUse.value).toBe('사무소');
  });
});

describe('건축물대장 조회 호출', () => {
  it('주소를 넘기고 항목별 진행 상태를 알린다', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse({ ...REGISTRY, sewage: null }));
    vi.stubGlobal('fetch', fetch);
    const steps: [LookupId, LookupStatus][] = [];
    const info = await fetchBuildingInfo('서울 송파구 위례광장로 199', {
      floorUnit: '4층 404호',
      onStepChange: (id, status) => steps.push([id, status]),
    });
    expect(fetch.mock.calls[0][0]).toContain(
      `/api/v1/building-registry?address=${encodeURIComponent('서울 송파구 위례광장로 199')}`
    );
    expect(steps).toEqual([
      ['title', 'loading'],
      ['floor', 'loading'],
      ['exclusiveArea', 'loading'],
      ['sewage', 'loading'],
      ['title', 'done'],
      ['floor', 'done'],
      ['exclusiveArea', 'done'],
      ['sewage', 'failed'],
    ]);
    expect(info.exclusiveAreaM2.value).toBe(93.6);
    expect(info.sewage.source).toBe('missing');
  });

  it.each([
    [400, ADDRESS_ERROR_NOTE],
    [502, LOOKUP_ERROR_NOTE],
  ])(
    '%s 응답이면 네 항목 모두 실패로 두고 빈칸으로 돌려준다',
    async (status, note) => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(jsonResponse({ detail: 'x' }, status))
      );
      const steps: LookupStatus[] = [];
      const info = await fetchBuildingInfo('입력 주소', {
        floorUnit: '4층',
        onStepChange: (_, value) => steps.push(value),
      });
      expect(steps.slice(4)).toEqual(['failed', 'failed', 'failed', 'failed']);
      expect(info.sourceNote).toBe(note);
      expect(info.address).toBe('입력 주소');
      expect(info.floorLabel).toBe('4층');
      expect(info.mainUse.source).toBe('missing');
      expect(info.parking.source).toBe('missing');
    }
  );

  it('네트워크 오류도 빈칸으로 돌려준다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('fetch failed'))
    );
    const info = await fetchBuildingInfo('입력 주소');
    expect(info.sourceNote).toBe(LOOKUP_ERROR_NOTE);
    expect(info.exclusiveAreaM2.source).toBe('missing');
  });

  it('취소는 그대로 거부한다', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockRejectedValue(
          new DOMException('조회가 취소됐습니다.', 'AbortError')
        )
    );
    await expect(fetchBuildingInfo('입력 주소')).rejects.toMatchObject({
      name: 'AbortError',
    });
  });
});

describe('호수 읽기와 실제 조회의 mockFail', () => {
  const HYPHEN: BuildingRegistryResponse = {
    ...REGISTRY,
    units: [
      {
        dong_name: null,
        unit_name: '401호',
        floor: '4층',
        use: '학원',
        use_detail: null,
        area_m2: 100.8,
      },
      {
        dong_name: null,
        unit_name: '401-1호',
        floor: '4층',
        use: '의원',
        use_detail: null,
        area_m2: 33.3,
      },
    ],
  };

  it('붙임표가 있는 호수를 그대로 찾는다', () => {
    expect(
      toBuildingInfo(HYPHEN, '', '4층 401-1호').exclusiveAreaM2.value
    ).toBe(33.3);
  });

  it('층 바로 뒤에 붙은 호수도 읽는다', () => {
    expect(toBuildingInfo(HYPHEN, '', '4층401호').exclusiveAreaM2.value).toBe(
      100.8
    );
  });

  it('실제 조회에서도 failLookups에 넣은 항목은 실패로 둔다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(REGISTRY)));
    const steps = new Map<LookupId, LookupStatus>();
    const info = await fetchBuildingInfo('서울 송파구 위례광장로 199', {
      floorUnit: '4층 404호',
      failLookups: ['floor'],
      onStepChange: (id, status) => steps.set(id, status),
    });
    expect(steps.get('floor')).toBe('failed');
    expect(steps.get('title')).toBe('done');
    expect(steps.get('exclusiveArea')).toBe('done');
    expect(steps.get('sewage')).toBe('done');
    expect(info.floorUse.source).toBe('missing');
    expect(info.exclusiveAreaM2.value).toBe(93.6);
  });
});
