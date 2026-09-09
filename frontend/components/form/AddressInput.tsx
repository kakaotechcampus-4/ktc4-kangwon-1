'use client';

import { useState } from 'react';
import Card from '@/components/ui/Card';
import Input from '@/components/ui/Input';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';

export default function AddressInput() {
  const [roadAddress, setRoadAddress] = useState('');
  const [floorUnit, setFloorUnit] = useState('');

  return (
    <Card
      className="w-full gap-4"
      style={{
        padding: '24px',
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow: 'none',
      }}
    >
      <p className="text-xl font-bold" style={{ color: colors.brand.dark }}>
        1. 공실 주소
      </p>

      <div className="flex w-full items-start gap-4">
        <div className="flex flex-1 flex-col items-start gap-2">
          <label
            htmlFor="road-address"
            className="text-[15px] font-medium text-gray-500"
          >
            도로명 주소
          </label>
          <Input
            id="road-address"
            value={roadAddress}
            onChange={(event) => setRoadAddress(event.target.value)}
            placeholder="서울특별시 관악구 봉천로 123"
          />
        </div>
        <div className="flex flex-1 flex-col items-start gap-2">
          <label
            htmlFor="floor-unit"
            className="text-[15px] font-medium text-gray-500"
          >
            층 / 호수
          </label>
          <Input
            id="floor-unit"
            value={floorUnit}
            onChange={(event) => setFloorUnit(event.target.value)}
            placeholder="1층 101호"
          />
        </div>
      </div>

      <div className="flex w-full justify-end gap-3 pt-2">
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
        >
          다음 · AI 판독 결과 확인
        </Button>
      </div>
    </Card>
  );
}
