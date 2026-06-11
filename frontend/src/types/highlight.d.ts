// CSS Custom Highlight API 최소 타입 선언.
// 일부 TS lib 버전에 Highlight / CSS.highlights 타입이 빠져 있어 보강한다.
declare class Highlight {
  constructor(...ranges: Range[]);
  add(range: Range): void;
  delete(range: Range): boolean;
  clear(): void;
}

interface HighlightRegistry extends Map<string, Highlight> {}

// CSS 네임스페이스에 highlights 추가
// eslint-disable-next-line no-var
declare namespace CSS {
  const highlights: HighlightRegistry;
}
