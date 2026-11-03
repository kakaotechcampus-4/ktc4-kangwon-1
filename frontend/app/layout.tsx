import type { Metadata } from 'next';
import { preload } from 'react-dom';
import './fonts/pretendard.css';
import './globals.css';
import StyledJsxRegistry from './StyledJsxRegistry';
import { PRETENDARD_LATIN_URL } from '@/styles/fonts';
import AuthProvider from '@/components/auth/AuthProvider';

export const metadata: Metadata = {
  title: '채움 · 공실에 맞는 업종을 찾아드립니다',
  description:
    '도면·임대조건·상권 데이터를 함께 분석해 공실에 가장 적합한 업종을 추천하는 임대인용 AI 서비스입니다.',
};

export default function RootLayout({ children }: LayoutProps<'/'>) {
  // 영문·숫자 묶음은 모든 화면에서 쓰므로 미리 받는다(나머지 묶음은 쓰일 때 받는다. app/fonts/pretendard.css).
  preload(PRETENDARD_LATIN_URL, {
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous',
  });
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <StyledJsxRegistry>
          <AuthProvider>{children}</AuthProvider>
        </StyledJsxRegistry>
      </body>
    </html>
  );
}
