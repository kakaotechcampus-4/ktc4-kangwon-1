import type { FacilityKey, FacilityState } from '@/lib/api/types';
import BuildingFieldRow from './BuildingFieldRow';
import SegmentedSelector from './SegmentedSelector';
import {
  FACILITY_STATE_LABELS,
  SPACE_FACILITY_LABELS,
  SPACE_FACILITY_ORDER,
} from './labels';

const FACILITY_STATE_OPTIONS = (
  Object.keys(FACILITY_STATE_LABELS) as FacilityState[]
).map((value) => ({ value, label: FACILITY_STATE_LABELS[value] }));

export default function FacilityRows({
  facilities,
  onChange,
}: {
  facilities: Record<FacilityKey, FacilityState>;
  onChange: (next: Record<FacilityKey, FacilityState>) => void;
}) {
  return (
    <>
      {SPACE_FACILITY_ORDER.map((key) => (
        <BuildingFieldRow
          key={key}
          label={SPACE_FACILITY_LABELS[key]}
          field={{
            value: facilities[key],
            registryValue: null,
            source: 'user',
          }}
          format={(value) => FACILITY_STATE_LABELS[value]}
          editable
          showSource={facilities[key] !== 'unknown'}
          editor={
            <SegmentedSelector
              options={FACILITY_STATE_OPTIONS}
              value={facilities[key]}
              onChange={(value) => onChange({ ...facilities, [key]: value })}
              ariaLabel={SPACE_FACILITY_LABELS[key]}
            />
          }
        />
      ))}
    </>
  );
}
