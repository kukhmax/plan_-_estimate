/**
 * A spoken number as text -> a number (V2-V, the voice input of the numeric fields).
 *
 * The owner says "пять точка два", "pięć przecinek dwa", "five point two", "три метра восемьдесят", "ноль семь пять", "сто двадцать злотых пятьдесят" and the
 * field gets 5.2 / 3.8 / 0.75 / 120.5. This is a plain table of words and a few rules, **no AI and no network**: a recognizer (the browser, the keyboard of the
 * phone) turns the voice into text, and this file turns the text into a number. The four languages of the application are understood at once (a field of a
 * Polish screen may be dictated in Russian), diacritics are optional ("piec" for "pięć"), digits the recognizer already wrote ("125,5", "2 50") are understood too.
 *
 * Two modes:
 * - `plain`: money, hours, percent, quantity. Units of length are ignored; "zł / злотых" works as the decimal mark.
 * - `length`: a size in **metres** as the result. "3 m 80" = 3.8; "250 cm" = 2.5; "2 50" = 2.5; a bare whole number below 10 is metres, from 10 up it is centimetres
 *   (the fields of sizes are typed in centimetres: "250" is 2.5 m).
 *
 * Rules without a decimal mark: "A B" is A.B ("два пятьдесят" = 2.50, "два семь" = 2.7), "A B C" with single digits is A.BC ("ноль семь пять" = 0.75);
 * "и / i / and" between two numbers is the decimal mark ("сто двадцать пять и пять" = 125.5) except inside "one hundred and twenty".
 * The result is always a string with a point; `null` means "not understood" (the screen then asks again or lets the owner type).
 */

export type SpeechMode = 'plain' | 'length';

type NumKind = 'zero' | 'unit' | 'teen' | 'tens' | 'hund' | 'mult100' | 'thousand';
type Unit = 'm' | 'cm' | 'mm';

type Token =
  | { t: 'num'; v: number; kind: NumKind }
  | { t: 'lit'; s: string }
  | { t: 'sep' }
  | { t: 'and' }
  | { t: 'half' }
  | { t: 'oneandhalf' }
  | { t: 'denom'; k: 1 | 2 | 3 }
  | { t: 'unit'; u: Unit }
  | { t: 'cur' }
  | { t: 'fill' }
  | { t: 'unk' };

/** Lower case, no diacritics, no apostrophes: "Pięć" = "piec", "п'ять" = "пять", "й" = "и", "ё" = "е". The words of the tables go through the same function. */
export function normalizeSpeech(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ł/g, 'l')
    .replace(/['’ʼ`´]/g, '');
}

const WORDS = new Map<string, Token>();

function add(token: Token, words: string): void {
  for (const word of words.split(/\s+/).filter(Boolean)) WORDS.set(normalizeSpeech(word), token);
}
function num(kind: NumKind, v: number, words: string): void {
  add({ t: 'num', v, kind }, words);
}

// --- numbers: Russian | Ukrainian | Polish | English --------------------------------------------------------------------------------------------
num('zero', 0, 'ноль нуль нулей zero');
const UNITS: [number, string][] = [
  [1, 'один одна одно одну одне jeden jedna jedno one'],
  [2, 'два две дві двe двух двох dwa dwie two'],
  [3, 'три трех трьох trzy three'],
  [4, 'четыре чотири cztery four'],
  [5, "пять п'ять piec five"],
  [6, 'шесть шість szesc six'],
  [7, 'семь сім siedem seven'],
  [8, 'восемь вісім osiem eight'],
  [9, "девять дев'ять dziewiec nine"],
];
for (const [v, words] of UNITS) num('unit', v, words);
const TEENS: [number, string][] = [
  [10, 'десять dziesiec ten'],
  [11, 'одиннадцать одинадцять jedenascie eleven'],
  [12, 'двенадцать дванадцять dwanascie twelve'],
  [13, 'тринадцать тринадцять trzynascie thirteen'],
  [14, 'четырнадцать чотирнадцять czternascie fourteen'],
  [15, "пятнадцать п'ятнадцять pietnascie fifteen"],
  [16, 'шестнадцать шістнадцять szesnascie sixteen'],
  [17, 'семнадцать сімнадцять siedemnascie seventeen'],
  [18, 'восемнадцать вісімнадцять osiemnascie eighteen'],
  [19, "девятнадцать дев'ятнадцять dziewietnascie nineteen"],
];
for (const [v, words] of TEENS) num('teen', v, words);
const TENS: [number, string][] = [
  [20, 'двадцать двадцять dwadziescia twenty'],
  [30, 'тридцать тридцять trzydziesci thirty'],
  [40, 'сорок czterdziesci forty'],
  [50, "пятьдесят п'ятдесят piecdziesiat fifty"],
  [60, 'шестьдесят шістдесят szescdziesiat sixty'],
  [70, 'семьдесят сімдесят siedemdziesiat seventy'],
  [80, 'восемьдесят вісімдесят osiemdziesiat eighty'],
  [90, "девяносто дев'яносто dziewiecdziesiat ninety"],
];
for (const [v, words] of TENS) num('tens', v, words);
const HUNDREDS: [number, string][] = [
  [100, 'сто sto'],
  [200, 'двести двісті dwiescie'],
  [300, 'триста trzysta'],
  [400, 'четыреста чотириста czterysta'],
  [500, "пятьсот п'ятсот piecset"],
  [600, 'шестьсот шістсот szescset'],
  [700, 'семьсот сімсот siedemset'],
  [800, 'восемьсот вісімсот osiemset'],
  [900, "девятьсот дев'ятсот dziewiecset"],
];
for (const [v, words] of HUNDREDS) num('hund', v, words);
num('mult100', 100, 'hundred');
num('thousand', 1000, 'тысяча тысячи тысяч тысячу тисяча тисячі тисяч тисячу tysiac tysiace tysiecy thousand');

// --- the decimal mark, "and", halves, tenths --------------------------------------------------------------------------------------------------
add({ t: 'sep' }, 'точка запятая кома крапка przecinek kropka point dot comma целых целая цілих цілі calych');
add({ t: 'and' }, 'и та i and с з z with');
add({ t: 'half' }, 'половина половины половиной половину половиною пів пол polowa polowy polowe polowa pol half');
add({ t: 'oneandhalf' }, 'полтора полторы півтора poltora');
add({ t: 'denom', k: 1 }, 'десятых десятая десятые десятой десятих десята десяті dziesiatych dziesiata tenths tenth');
add({ t: 'denom', k: 2 }, 'сотых сотая сотые сотой сотих сота соті setnych setna hundredths hundredth');
add({ t: 'denom', k: 3 }, 'тысячных тысячная тисячних tysiecznych thousandths thousandth');

// --- units of length, money and words that say nothing ------------------------------------------------------------------------------------------
add({ t: 'unit', u: 'm' }, 'метр метра метров метры метре метри метрів м m meter meters metre metres metr metra metrow metry');
add({ t: 'unit', u: 'cm' }, 'сантиметр сантиметра сантиметров сантиметры сантиметри сантиметрів см cm centymetr centymetra centymetrow centymetry centimeter centimeters centimetre centimetres');
add({ t: 'unit', u: 'mm' }, 'миллиметр миллиметра миллиметров миллиметры міліметр міліметри міліметрів мм mm milimetr milimetra milimetrow milimetry millimeter millimeters millimetre millimetres');
add({ t: 'cur' }, 'злотый злотых злотые злотого złoty złotych złote złotego zl zloty zlotych zlote zlotego zlotys pln');
add(
  { t: 'fill' },
  'грош грошей гроши grosz groszy groszow грошів процент процента процентов процентів procent procentow percent % час часа часов годин години godzina godziny godzin hour hours ч h a the',
);

const TOKEN_SPLIT = /[^\p{L}\p{N}.,%]+/u;

function tokenize(text: string): Token[] {
  const spaced = normalizeSpeech(text)
    .replace(/(\d)\s*([\p{L}%])/gu, '$1 $2')
    .replace(/([\p{L}%])(\d)/gu, '$1 $2')
    .replace(/[.,]/g, (mark, at: number, whole: string) => (/\d/.test(whole[at - 1] ?? '') && /\d/.test(whole[at + 1] ?? '') ? mark : ' ')); // a point or a comma that is not between digits is only punctuation (no look-behind: old iOS WebViews)
  const tokens: Token[] = [];
  for (const raw of spaced.split(TOKEN_SPLIT)) {
    if (raw === '') continue;
    if (/^\d+([.,]\d+)?$/.test(raw)) {
      tokens.push({ t: 'lit', s: raw.replace(',', '.') });
      continue;
    }
    tokens.push(WORDS.get(raw) ?? { t: 'unk' });
  }
  return tokens;
}

// --- groups of number words: "сто двадцать пять" = 125 -----------------------------------------------------------------------------------------------

interface Parsed {
  v: number;
  next: number;
}

function kindOf(token: Token | undefined): NumKind | null {
  return token && token.t === 'num' ? token.kind : null;
}
function valueOf(token: Token): number {
  return token.t === 'num' ? token.v : 0;
}

function belowThousand(tokens: Token[], start: number): Parsed | null {
  let j = start;
  let v = 0;
  let got = false;
  if (kindOf(tokens[j]) === 'unit' && kindOf(tokens[j + 1]) === 'mult100') {
    v = valueOf(tokens[j]) * 100;
    j += 2;
    got = true;
  } else if (kindOf(tokens[j]) === 'mult100') {
    v = 100;
    j += 1;
    got = true;
  } else if (kindOf(tokens[j]) === 'hund') {
    v = valueOf(tokens[j]);
    j += 1;
    got = true;
  }
  let k = j;
  if (got && tokens[k]?.t === 'and' && ['teen', 'tens', 'unit'].includes(kindOf(tokens[k + 1]) ?? '')) k += 1; // "one hundred AND twenty"
  const kind = kindOf(tokens[k]);
  if (kind === 'teen') {
    v += valueOf(tokens[k]);
    j = k + 1;
    got = true;
  } else if (kind === 'tens') {
    v += valueOf(tokens[k]);
    j = k + 1;
    got = true;
    if (kindOf(tokens[j]) === 'unit') {
      v += valueOf(tokens[j]);
      j += 1;
    }
  } else if (kind === 'unit') {
    v += valueOf(tokens[k]);
    j = k + 1;
    got = true;
  }
  return got ? { v, next: j } : null;
}

function group(tokens: Token[], start: number): Parsed | null {
  if (kindOf(tokens[start]) === 'zero') return { v: 0, next: start + 1 };
  const head = belowThousand(tokens, start);
  let total = 0;
  let j = start;
  if (head && kindOf(tokens[head.next]) === 'thousand') {
    total = head.v * 1000;
    j = head.next + 1;
  } else if (!head && kindOf(tokens[start]) === 'thousand') {
    total = 1000;
    j = start + 1;
  } else {
    return head;
  }
  const tail = belowThousand(tokens, tokens[j]?.t === 'and' && kindOf(tokens[j + 1]) !== null ? j + 1 : j);
  if (tail) {
    total += tail.v;
    j = tail.next;
  }
  return { v: total, next: j };
}

// --- items: numbers, marks and units in the order they were said ---------------------------------------------------------------------------------

type Item =
  | { k: 'n'; int: string; frac: string | null; word: boolean } // a number; `frac` when it was written with a point ("5,7")
  | { k: 'sep' }
  | { k: 'and' }
  | { k: 'half' }
  | { k: 'oneandhalf' }
  | { k: 'denom'; n: 1 | 2 | 3 }
  | { k: 'unit'; u: Unit }
  | { k: 'unk' };

function toItems(tokens: Token[]): Item[] {
  const items: Item[] = [];
  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i];
    if (token.t === 'num') {
      const parsed = group(tokens, i);
      if (parsed) {
        items.push({ k: 'n', int: String(parsed.v), frac: null, word: true });
        i = parsed.next;
        continue;
      }
      items.push({ k: 'unk' }); // "hundred" with nothing else is a group; "and"-less leftovers cannot start one
      i += 1;
      continue;
    }
    i += 1;
    if (token.t === 'lit') {
      const [whole, fraction] = token.s.split('.');
      items.push({ k: 'n', int: whole, frac: fraction ?? null, word: false });
    } else if (token.t === 'sep' || token.t === 'cur') items.push({ k: 'sep' });
    else if (token.t === 'and') items.push({ k: 'and' });
    else if (token.t === 'half') items.push({ k: 'half' });
    else if (token.t === 'oneandhalf') items.push({ k: 'oneandhalf' });
    else if (token.t === 'denom') items.push({ k: 'denom', n: token.k });
    else if (token.t === 'unit') items.push({ k: 'unit', u: token.u });
    else if (token.t === 'unk') items.push({ k: 'unk' });
    // `fill` says nothing
  }
  return items;
}

function trimUnknown(items: Item[]): Item[] | null {
  let a = 0;
  let b = items.length;
  while (a < b && items[a].k === 'unk') a += 1;
  while (b > a && items[b - 1].k === 'unk') b -= 1;
  const kept = items.slice(a, b);
  return kept.some((item) => item.k === 'unk') ? null : kept; // a word nobody knows inside the number: it was probably misheard
}

/** A run of items with no unit in it as a decimal string ("5.23") or null. */
function readRun(items: Item[], mode: SpeechMode, allowGroupsAbove100InFraction = false): string | null {
  // "1 200" as the recognizer writes thousands (plain mode only)
  const merged: Item[] = [];
  for (const item of items) {
    const last = merged[merged.length - 1];
    if (
      mode === 'plain' && item.k === 'n' && !item.word && item.int.length === 3 && item.frac === null &&
      last && last.k === 'n' && !last.word && last.frac === null && last.int.length <= 3
    ) {
      merged[merged.length - 1] = { k: 'n', int: last.int + item.int, frac: null, word: false };
    } else {
      merged.push(item);
    }
  }
  let int: string | null = null;
  let frac = '';
  let inFraction = false;
  let explicit = false;
  let denom: number | null = null;
  for (const item of merged) {
    if (item.k === 'n') {
      if (int === null) {
        int = item.int;
        if (item.frac !== null) {
          frac = item.frac;
          inFraction = true;
          explicit = true;
        }
      } else if (!inFraction) {
        // "A B": the second number is the fraction ("два пятьдесят")
        if (item.word && Number(item.int) >= 100 && !allowGroupsAbove100InFraction) return null;
        inFraction = true;
        frac += item.int + (item.frac ?? '');
      } else {
        if (item.word && !explicit && Number(item.int) >= 100 && !allowGroupsAbove100InFraction) return null;
        frac += item.int + (item.frac ?? '');
      }
    } else if (item.k === 'sep' || item.k === 'and') {
      if (int === null) int = '0';
      inFraction = true;
      explicit = true;
    } else if (item.k === 'half') {
      if (int === null) int = '0';
      inFraction = true;
      frac += '5';
    } else if (item.k === 'oneandhalf') {
      int = '1';
      inFraction = true;
      frac = '5';
    } else if (item.k === 'denom') {
      if (!inFraction) {
        frac = int ?? ''; // "две десятых" with no whole part: the number said is the fraction
        int = '0';
      }
      inFraction = true;
      denom = item.n;
    }
  }
  if (int === null) return null;
  if (denom !== null) frac = frac.padStart(denom, '0');
  const whole = int.replace(/^0+(?=\d)/, '');
  if (whole.length > 9 || frac.length > 6) return null;
  return frac === '' ? whole : `${whole}.${frac}`;
}

function clean(n: number): string {
  return String(Number(n.toFixed(4)));
}

const MM: Record<Unit, number> = { m: 1000, cm: 10, mm: 1 };
const SMALLER: Record<Unit, Unit | null> = { m: 'cm', cm: 'mm', mm: null };

/** "три метра восемьдесят сантиметров" -> metres. */
function readWithUnits(items: Item[]): string | null {
  const runs: { items: Item[]; unit: Unit | null }[] = [];
  let current: Item[] = [];
  for (const item of items) {
    if (item.k === 'unit') {
      runs.push({ items: current, unit: item.u });
      current = [];
    } else {
      current.push(item);
    }
  }
  if (current.length > 0) runs.push({ items: current, unit: null });
  let total = 0;
  let previous: Unit | null = null;
  for (const run of runs) {
    let unit = run.unit;
    if (unit === null) {
      unit = previous ? SMALLER[previous] : null; // "3 m 80": what follows a metre is centimetres
      if (unit === null) return null;
    }
    let quantity: number;
    if (run.items.length === 0) {
      if (unit !== 'm') return null;
      quantity = 1; // "метр двадцать"
    } else {
      const read = readRun(run.items, 'length', true);
      if (read === null) return null;
      quantity = Number(read);
    }
    total += quantity * MM[unit];
    previous = run.unit ?? unit;
  }
  return total > 0 || runs.length > 0 ? clean(total / 1000) : null;
}

/**
 * A spoken number. `text` is what the recognizer wrote; the result is a decimal string with a point ("125.5"), in metres for `length`, or null.
 */
export function parseSpokenNumber(text: string, mode: SpeechMode = 'plain'): string | null {
  const items = trimUnknown(toItems(tokenize(text)));
  if (items === null || !items.some((item) => item.k === 'n' || item.k === 'half' || item.k === 'oneandhalf' || (item.k === 'unit' && mode === 'length'))) return null;
  if (mode === 'length') {
    if (items.some((item) => item.k === 'unit')) return readWithUnits(items);
    const read = readRun(items, 'length');
    if (read === null) return null;
    if (read.includes('.')) return read; // "2 50", "3,8": metres as spoken
    const whole = Number(read);
    return whole < 10 ? read : clean(whole / 100); // 250 is 2.5 m, as the field is typed
  }
  return readRun(items.filter((item) => item.k !== 'unit'), 'plain');
}

/** The first of several alternatives (a recognizer gives a few) that is a number. */
export function parseSpokenAlternatives(texts: readonly string[], mode: SpeechMode = 'plain'): { text: string; value: string } | null {
  for (const text of texts) {
    const value = parseSpokenNumber(text, mode);
    if (value !== null) return { text, value };
  }
  return null;
}
