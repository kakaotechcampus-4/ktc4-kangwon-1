import { describe, expect, it } from 'vitest';
import { reportPdfTitle } from '@/lib/api/reportPdf';

describe('reportPdfTitle', () => {
  it('실제 리포트는 서비스명·주소·분석일로 이름을 짓는다', () => {
    expect(
      reportPdfTitle({
        example: false,
        address: '서울 송파구 위례광장로 199 1층',
        analyzedDate: '2026.11.04',
      })
    ).toBe(
      '채움 업종분석 리포트 - 서울 송파구 위례광장로 199 1층 (2026.11.04)'
    );
  });

  it('예시 리포트는 예시라고 밝히고 날짜를 붙이지 않는다', () => {
    expect(
      reportPdfTitle({
        example: true,
        address: '서울 송파구 오금로 404 1층',
        analyzedDate: '2026.10.30',
      })
    ).toBe('채움 예시 리포트 - 서울 송파구 오금로 404 1층');
  });

  it('파일 이름에 쓸 수 없는 글자는 빼고 빈칸을 정리한다', () => {
    expect(
      reportPdfTitle({
        example: false,
        address: '  서울 "중구"  세종대로 1/2:3*?<>|  ',
        analyzedDate: '2026.11.04',
      })
    ).toBe('채움 업종분석 리포트 - 서울 중구 세종대로 1 2 3 (2026.11.04)');
  });

  it('분석일이나 주소가 없으면 그 부분만 뺀다', () => {
    expect(
      reportPdfTitle({
        example: false,
        address: '서울 마포구 양화로 1',
        analyzedDate: '',
      })
    ).toBe('채움 업종분석 리포트 - 서울 마포구 양화로 1');
    expect(
      reportPdfTitle({ example: false, address: ' ', analyzedDate: '' })
    ).toBe('채움 업종분석 리포트');
  });
});
