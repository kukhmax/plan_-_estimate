/** V2-14 — the link for the electrician and the plumber: the owner's side and the open page of the craftsman (mirrors backend/app/schemas/trade_link.py). */
import type { Locale } from '../utils/locale';

export type LinkTrade = 'ELECTRIC' | 'PLUMBING';
export type PositionUnit = 'PCS' | 'LM';

export const LINK_TRADES: readonly LinkTrade[] = ['ELECTRIC', 'PLUMBING'];

/** The limits of the server (backend/app/domain/rules/trade_checklist.py): the form stops the input, the server decides. */
export const TRADE_LINK_LIMITS = { note: 200, name: 80, own_per_room: 30, comment: 1000, master_name: 80 } as const;

export interface TypicalAnswer {
  key: string;
  unit: PositionUnit;
  quantity: string | null;
  note: string | null;
}

export interface OwnAnswer {
  name: string;
  quantity: string;
  unit: PositionUnit;
  note: string | null;
}

export interface PositionInfo {
  key: string;
  unit: PositionUnit;
}

// --- the owner's side ---------------------------------------------------------------------------------------------------------

export interface TradeLinkInfo {
  trade: LinkTrade;
  language: Locale;
  owner_note: string | null;
  created_at: string;
  expires_at: string;
  last_viewed_at: string | null;
  view_count: number;
  expired: boolean;
  answers_count: number;
  submissions_count: number;
  last_submitted_at: string | null;
}

export interface TradeLinksResponse {
  electric: TradeLinkInfo | null;
  plumbing: TradeLinkInfo | null;
}

export interface TradeLinkCreated {
  link: TradeLinkInfo;
  token: string;
}

export interface OwnerRoomAnswers {
  room_id: string;
  room_name: string;
  typical: TypicalAnswer[];
  own: OwnAnswer[];
  updated_at: string | null;
}

export interface TradeSubmission {
  id: string;
  master_name: string;
  answers_count: number;
  created_at: string;
}

export interface TradeAnswersResponse {
  trade: LinkTrade;
  positions: PositionInfo[];
  rooms: OwnerRoomAnswers[];
  submissions: TradeSubmission[];
}

// --- the open page ------------------------------------------------------------------------------------------------------------

export interface PortalTradeContractor {
  name: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
}

export interface PortalTradeRoom {
  id: string;
  name: string;
  length: string | null;
  width: string | null;
  height: string | null;
  floor_area: string | null;
  perimeter: string | null;
  typical: TypicalAnswer[];
  own: OwnAnswer[];
}

export interface PortalTradePage {
  link: { expires_at: string; language: Locale };
  lang: Locale;
  trade: LinkTrade;
  contractor: PortalTradeContractor;
  project_name: string;
  owner_note: string | null;
  positions: PositionInfo[];
  rooms: PortalTradeRoom[];
  submissions_count: number;
  last_submitted_at: string | null;
}

export interface TypicalWrite {
  key: string;
  quantity: string | null;
  note: string | null;
}

export interface OwnWrite {
  name: string;
  quantity: string | null;
  unit: PositionUnit;
  note: string | null;
}

export interface RoomWrite {
  typical: TypicalWrite[];
  own: OwnWrite[];
}

export function tradeLinkUrl(origin: string, token: string): string {
  return `${origin.replace(/\/$/, '')}/m#${token}`;
}
