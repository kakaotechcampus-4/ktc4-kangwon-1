'use client';

import { useState, type ReactNode } from 'react';
import { useServerInsertedHTML } from 'next/navigation';
import { StyleRegistry, createStyleRegistry } from 'styled-jsx';

/**
 * <style jsx> 스타일을 서버 HTML에 같이 넣는다. 이게 없으면 App Router에서는
 * 스타일이 JS가 뜬 뒤에야 붙어서, 새로고침 직후 화면이 잠깐 깨져 보인다.
 * https://nextjs.org/docs/app/guides/css-in-js#styled-jsx
 */
export default function StyledJsxRegistry({
  children,
}: {
  children: ReactNode;
}) {
  // 요청마다 한 번만 만든다.
  const [registry] = useState(() => createStyleRegistry());

  useServerInsertedHTML(() => {
    const styles = registry.styles();
    registry.flush();
    return <>{styles}</>;
  });

  return <StyleRegistry registry={registry}>{children}</StyleRegistry>;
}
