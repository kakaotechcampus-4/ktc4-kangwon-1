const UNSAFE_FILE_CHARACTERS = /[\\/:*?"<>|\u0000-\u001f]/g;

function clean(text: string): string {
  return text.replace(UNSAFE_FILE_CHARACTERS, ' ').replace(/\s+/g, ' ').trim();
}

export function reportPdfTitle({
  example,
  address,
  analyzedDate,
}: {
  example: boolean;
  address: string;
  analyzedDate: string;
}): string {
  const base = example ? '채움 예시 리포트' : '채움 업종분석 리포트';
  const place = clean(address);
  const day = example ? '' : clean(analyzedDate);
  const title = place ? `${base} - ${place}` : base;
  return day ? `${title} (${day})` : title;
}
