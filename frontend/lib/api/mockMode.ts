/**
 * 프론트 mock 모드 스위치. frontend/.env.local에 NEXT_PUBLIC_MOCK_MODE=true를
 * 넣으면 백엔드를 부르지 않고 주소 입력 → 상가 정보 확인 → 분석 진행 → 리포트를
 * 처음부터 끝까지 mock 데이터로 돈다. 끄면(또는 비우면) 실제 백엔드를 호출한다.
 *
 * NEXT_PUBLIC_ 값은 빌드 시점에 코드에 박히므로, 바꾼 뒤에는 개발 서버를
 * 다시 띄워야 한다.
 */
export const MOCK_MODE = process.env.NEXT_PUBLIC_MOCK_MODE === 'true';
