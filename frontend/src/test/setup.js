import '@testing-library/jest-dom/vitest';

// Mock window.matchMedia for components that check media queries
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock window.history.replaceState for RequirementsList URL sync
if (!window.history.replaceState) {
  window.history.replaceState = vi.fn();
}

// Silence console.error for expected React warnings in tests
const originalConsoleError = console.error;
beforeEach(() => {
  console.error = (...args) => {
    if (
      typeof args[0] === 'string' &&
      args[0].includes('Warning: ReactDOM.render is no longer supported')
    ) {
      return;
    }
    originalConsoleError(...args);
  };
});
afterEach(() => {
  console.error = originalConsoleError;
  vi.restoreAllMocks();
});
