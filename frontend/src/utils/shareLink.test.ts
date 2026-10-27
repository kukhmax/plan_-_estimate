import { afterEach, describe, expect, it, vi } from 'vitest';
import { shareLink } from './shareLink';

const LINK = 'https://plan-estimate.pl/m#secret';
const TEXT = 'Link do listy punktów i tras (Hydraulik):';

afterEach(() => {
  delete window.Telegram;
  Object.defineProperty(navigator, 'share', { value: undefined, configurable: true });
});

describe('shareLink', () => {
  it('puts the description before the address in the share window of Telegram', () => {
    const open = vi.fn();
    window.Telegram = { WebApp: { openTelegramLink: open } } as unknown as typeof window.Telegram;
    shareLink(LINK, TEXT, vi.fn());
    const opened = decodeURIComponent(open.mock.calls[0][0] as string);
    expect(opened.indexOf(TEXT)).toBeGreaterThan(-1);
    expect(opened.indexOf(TEXT)).toBeLessThan(opened.indexOf(LINK)); // what Telegram shows first is the `url` parameter
    expect(open.mock.calls[0][0]).toMatch(/^https:\/\/t\.me\/share\/url\?url=.+&text=.+/);
  });

  it('sends one text with the description on the first line and the address on the second to the share sheet', () => {
    const share = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    shareLink(LINK, TEXT, vi.fn());
    expect(share).toHaveBeenCalledWith({ text: `${TEXT}\n${LINK}` });
  });

  it('copies the address when there is nothing to share with', () => {
    const copy = vi.fn();
    shareLink(LINK, TEXT, copy);
    expect(copy).toHaveBeenCalledTimes(1);
  });
});
