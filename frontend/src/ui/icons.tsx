/** A few hand-drawn 24px line icons. Stroke colour comes from currentColor. */
const P: Record<string, string> = {
  overview: 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z',
  releases: 'M12 3 3 8l9 5 9-5-9-5zM3 13l9 5 9-5M3 17.5 12 22l9-4.5',
  incidents: 'M12 4 2.8 19.5h18.4L12 4zM12 10v4.5M12 17.2v.1',
  gates: 'M12 3 4.5 6v5.6c0 4.4 3.1 7.9 7.5 9.4 4.4-1.5 7.5-5 7.5-9.4V6L12 3zM8.8 12l2.3 2.3 4.2-4.6',
  ledger: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
  system: 'M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M6 6h12v12H6zM10 10h4v4h-4z',
  check: 'M5 12.5 10 17 19 7.5',
  x: 'M6 6l12 12M18 6 6 18',
  ai: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3zM18.5 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2z',
  seal: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5zM14 3v5h5M9 14l2 2 4-4',
  play: 'M7 5v14l11-7L7 5z',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
};

export function Icon({ name, className = 'ico' }: { name: keyof typeof P | string; className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" aria-hidden="true"><path d={P[name] ?? ''} /></svg>;
}
