import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class NoopIntersectionObserver extends NoopResizeObserver {
  takeRecords() {
    return [];
  }
}

globalThis.ResizeObserver ??= NoopResizeObserver;
globalThis.IntersectionObserver ??=
  NoopIntersectionObserver as unknown as typeof IntersectionObserver;
window.scrollTo = () => {};
