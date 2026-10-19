/**
 * Stage 20D -- rules of the source that the product depends on, read from the files themselves:
 *  - every user-facing string comes from the locale dictionaries (no words in JSX, no literal placeholder / title / alt),
 *  - no price, VAT rate or legal text in a component (they come from the backend),
 *  - no debug leftovers, no raw HTML injection, no eval.
 * A component that breaks a rule fails this file, naming the line.
 */
import { describe, expect, it } from 'vitest';

// every source file of the application, as text (Vite reads them; no Node types needed)
const raw = import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

const files = Object.entries(raw)
  .filter(([path]) => !/\.test\.(ts|tsx)$/.test(path) && !path.includes('/src/test/') && !path.includes('/src/locales/') && !path.includes('/src/audit/'))
  .map(([path, text]) => ({ path: path.replace('/src/', ''), lines: text.split('\n') }));

function hits(pattern: RegExp, allow: (path: string, line: string) => boolean = () => false): string[] {
  const found: string[] = [];
  for (const { path, lines } of files) {
    lines.forEach((line, index) => {
      if (/^\s*(\*|\/\*)/.test(line)) return; // a comment
      const code = line.replace(/\/\/.*$/, '');
      if (pattern.test(code) && !allow(path, line)) found.push(`${path}:${index + 1}: ${line.trim().slice(0, 100)}`);
    });
  }
  return found;
}

describe('the source of the application', () => {
  it('reads the whole source (the guard is not empty)', () => {
    expect(files.length).toBeGreaterThan(90);
  });

  it('has no words written into JSX (except the names of the two languages, which are written in their own language)', () => {
    const text = />\s*[A-Za-zĄĘŁŃÓŚŹŻąęłńóśźżА-Яа-я][^<>{}=;]{2,}<\//;
    expect(hits(text, (path, line) => path === 'components/CalendarSettingsForm.tsx' && /(Polski|Русский)/.test(line))).toEqual([]);
  });

  it('has no literal placeholder, title or alt', () => {
    expect(hits(/\b(placeholder|title|alt)="[A-Za-zĄĘŁŃÓŚŹŻąęłńóśźżА-Яа-я]/)).toEqual([]);
  });

  it('has no price, currency amount or VAT rate in a component (money comes formatted from the server)', () => {
    const money = /(\b[0-9]+([.,][0-9]+)?\s?(zł|PLN|EUR)(?![A-Za-z]))|(\b(1\.23|0\.23|1\.08|0\.08)\b)/;
    expect(hits(money)).toEqual([]);
  });

  it('has no legal text or norm written into the code (it comes from the knowledge base)', () => {
    expect(hits(/\b(Kodeks|Prawo budowlane|PN-EN|PN-B|art\.\s?\d+)/)).toEqual([]);
  });

  it('has no debug leftovers, raw HTML injection or eval', () => {
    expect(hits(/console\.(log|debug)|\bdebugger\b|dangerouslySetInnerHTML|\beval\(|\.innerHTML\b/)).toEqual([]);
  });

  it('gives a checkbox a label that is a whole touch target (44 px), not the 13 px box (found by the audit, 20D)', () => {
    const bad: string[] = [];
    for (const { path, lines } of files) {
      lines.forEach((line, index) => {
        if (!/<label\b/.test(line)) return;
        const end = lines.slice(index, index + 14).findIndex((l) => l.includes('</label>'));
        if (end < 0) return;
        const block = lines.slice(index, index + end + 1).join('\n');
        if (/type="(checkbox|radio)"/.test(block) && !/min-h-(11|\[44px\])/.test(line)) bad.push(`${path}:${index + 1}`);
      });
    }
    expect(bad).toEqual([]);
  });

  it('gives the text inputs and selects of the forms a 44 px height', () => {
    expect(hits(/className="w-full border border-slate-200 rounded-lg px-(3|2\.5) py-(2|1\.5) (?!min-h)/, (_p, line) => /min-h-(11|12|16|20|24|\[44px\])/.test(line))).toEqual([]);
  });

  it('gives every button a minimum height of 44 px (a padding alone does not make a touch target)', () => {
    const bad: string[] = [];
    for (const { path, lines } of files) {
      lines.forEach((line, index) => {
        if (!/<button\b/.test(line)) return;
        let tag = line;
        for (let next = index + 1; next < Math.min(index + 14, lines.length); next += 1) {
          if (/<\/button>|^\s*<[A-Za-z]/.test(lines[next])) break;
          tag += `\n${lines[next]}`;
        }
        const cls = /className=(?:"([^"]*)"|\{`([^`]*)`\})/.exec(tag);
        const value = cls ? (cls[1] ?? cls[2] ?? '') : '';
        if (value && /\b(py-1|py-1\.5|py-2|p-1|p-2)\b/.test(value) && !/min-h-(11|12|\[44px\])|\bh-(11|12)\b/.test(value)) bad.push(`${path}:${index + 1}`);
      });
    }
    expect(bad).toEqual([]);
  });

  it('has no 40 px control left: buttons and rows are min-h-11 (44 px) (20D)', () => {
    // the language switcher is small BY THE OWNER'S DECISION (it sits in the header; Stage 16K): the one exception
    expect(hits(/\bmin-h-([5-9]|10)\b/, (path, line) => path === 'App.tsx' && /min-h-9 min-w-9 text-xs px-2 rounded-md/.test(line))).toEqual([]);
  });

  it('keeps no secret-looking value in the code', () => {
    expect(hits(/(bot[0-9]{6,}:[A-Za-z0-9_-]{20,})|(sk_live_)|(AKIA[0-9A-Z]{16})|(-----BEGIN [A-Z ]*PRIVATE KEY)/)).toEqual([]);
  });
});
