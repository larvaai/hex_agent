import "@testing-library/jest-dom/vitest";

// jsdom lacks these APIs that @xyflow/react and @tanstack/react-virtual touch — provide mocks
// that actually report the (test-mocked) element size so the virtualizer computes a window.
class ResizeObserverMock {
  private cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }
  observe(el: Element) {
    const rect = el.getBoundingClientRect();
    this.cb([{ target: el, contentRect: rect } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

if (!globalThis.matchMedia) {
  // @ts-expect-error jsdom global
  globalThis.matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
