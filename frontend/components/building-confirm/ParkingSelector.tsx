import type { ParkingAvailability } from '@/lib/api/building';
import SegmentedSelector from './SegmentedSelector';
import { PARKING_LABELS } from './labels';

const OPTIONS = (Object.keys(PARKING_LABELS) as ParkingAvailability[]).map(
  (value) => ({ value, label: PARKING_LABELS[value] })
);

type ParkingSelectorProps = {
  value: ParkingAvailability | null;
  onChange: (value: ParkingAvailability) => void;
};

/** 주차 가능 여부 — 가능 / 불가 / 모름. "모름"도 답으로 받는다. */
export default function ParkingSelector({
  value,
  onChange,
}: ParkingSelectorProps) {
  return (
    <SegmentedSelector
      options={OPTIONS}
      value={value}
      onChange={onChange}
      ariaLabel="주차 가능 여부"
    />
  );
}
