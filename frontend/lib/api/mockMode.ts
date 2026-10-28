/**
 * 프론트 mock 모드 스위치. frontend/.env.local에 NEXT_PUBLIC_MOCK_MODE=true를
 * 넣으면 분석은 프론트 목업으로 진행하고, 건축물 확인은 백엔드의 mock=true 응답을 쓴다.
 * 실제 건축물 HUB·분석 외부 호출은 발생하지 않는다. 끄면 실제 백엔드를 호출한다.
 *
 * NEXT_PUBLIC_ 값은 빌드 시점에 코드에 박히므로, 바꾼 뒤에는 개발 서버를
 * 다시 띄워야 한다.
 */
export const MOCK_MODE = process.env.NEXT_PUBLIC_MOCK_MODE === 'true';
