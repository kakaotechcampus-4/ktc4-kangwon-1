import { mockProperty } from '@/lib/mockData/property';
import type { ChangeEvent } from 'react';
import Card from '@/components/ui/Card';
import Input from '@/components/ui/Input';
import { colors } from '@/styles/tokens';

type AddressInputProps = {
  roadAddress: string;
  onRoadAddressChange: (value: string) => void;
  floorUnit: string;
  onFloorUnitChange: (value: string) => void;
};

export default function AddressInput({
  roadAddress,
  onRoadAddressChange,
  floorUnit,
  onFloorUnitChange,
}: AddressInputProps) {
  return (
    <Card
      className="w-full gap-4"
      style={{
        padding: 'clamp(18px, 5vw, 32px)',
        borderRadius: '24px',
        borderWidth: '0px',
      }}
    >
      <p className="text-xl font-bold" style={{ color: colors.brand.dark }}>
        1. 공실 주소
      </p>

      <div className="flex w-full min-w-0 flex-col items-start gap-4 sm:flex-row">
        <div className="flex w-full min-w-0 flex-col items-start gap-2 sm:flex-1">
          <label
            htmlFor="road-address"
            className="text-15 font-medium text-gray-500"
          >
            도로명 주소
          </label>
          <Input
            id="road-address"
            value={roadAddress}
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              onRoadAddressChange(event.target.value)
            }
            placeholder={mockProperty.address}
          />
        </div>
        <div className="flex w-full min-w-0 flex-col items-start gap-2 sm:flex-1">
          <label
            htmlFor="floor-unit"
            className="text-15 font-medium text-gray-500"
          >
            층 / 호수
          </label>
          <Input
            id="floor-unit"
            value={floorUnit}
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              onFloorUnitChange(event.target.value)
            }
            placeholder={mockProperty.floorUnit}
          />
        </div>
      </div>
    </Card>
  );
}
