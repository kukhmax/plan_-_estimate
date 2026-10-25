import { describe, expect, it } from 'vitest';
import { normalizeSpeech, parseSpokenAlternatives, parseSpokenNumber } from './speechNumber';

// V2-V — a spoken number as text becomes a number: four languages, no AI, no network.

const plain = (text: string) => parseSpokenNumber(text, 'plain');
const metres = (text: string) => parseSpokenNumber(text, 'length');

describe('the words of the four languages', () => {
  it.each([
    // [text, the number]
    ['dwadzieścia trzy', '23'], ['двадцать три', '23'], ['двадцять три', '23'], ['twenty three', '23'], ['twenty-three', '23'],
    ['sto dwadzieścia pięć', '125'], ['сто двадцать пять', '125'], ['сто двадцять п’ять', '125'], ['one hundred twenty five', '125'], ['one hundred and twenty five', '125'],
    ['tysiąc dwieście', '1200'], ['одна тысяча двести', '1200'], ['тисяча двісті', '1200'], ['one thousand two hundred', '1200'], ['тысяча', '1000'],
    ['dwa tysiące pięćset', '2500'], ['две тысячи двадцать', '2020'], ['сто тысяч', '100000'],
    ['zero', '0'], ['ноль', '0'], ['нуль', '0'],
    ['jedenaście', '11'], ['девятнадцать', '19'], ['девяносто девять', '99'], ['dziewięćset dziewięćdziesiąt dziewięć', '999'],
    ['  PIĘĆ  ', '5'], ['piec', '5'], // capitals and missing diacritics
  ])('%s = %s', (text, expected) => {
    expect(plain(text)).toBe(expected);
  });
});

describe('the decimal mark and the pairs', () => {
  it.each([
    ['пять точка два', '5.2'], ['pięć przecinek dwa', '5.2'], ['five point two', '5.2'], ['п’ять крапка два', '5.2'], ['пять запятая два', '5.2'],
    ['сто двадцать пять и пять', '125.5'], ['sto dwadzieścia pięć i pięć', '125.5'], ['one hundred twenty five and five', '125.5'],
    ['пять двадцать три', '5.23'], ['пять точка двадцать три', '5.23'], ['pięć dwadzieścia trzy', '5.23'],
    ['ноль семь пять', '0.75'], ['zero siedem pięć', '0.75'], ['zero seven five', '0.75'], ['ноль пять', '0.5'], ['zero zero pięć', '0.05'],
    ['два пятьдесят', '2.50'], ['два семь', '2.7'], ['dwa pięćdziesiąt', '2.50'],
    ['пять точка ноль семь', '5.07'], ['точка пять', '0.5'], ['przecinek dwa', '0.2'],
    ['пять с половиной', '5.5'], ['dwa i pół', '2.5'], ['two and a half', '2.5'], ['полтора', '1.5'], ['півтора', '1.5'], ['половина', '0.5'], ['pół', '0.5'],
    ['пять целых две десятых', '5.2'], ['пять целых пять сотых', '5.05'], ['dwa i pięć dziesiątych', '2.5'], ['two point five tenths', '2.5'], ['две десятых', '0.2'], ['пять сотых', '0.05'],
  ])('%s = %s', (text, expected) => {
    expect(plain(text)).toBe(expected);
  });

  it('understands the digits a recognizer already wrote, with a comma or a point, and its thousands', () => {
    expect(plain('125,5')).toBe('125.5');
    expect(plain('125.5')).toBe('125.5');
    expect(plain('2 50')).toBe('2.50');
    expect(plain('1 200')).toBe('1200');
    expect(plain('12 500')).toBe('12500');
    expect(plain('сто 20 пять')).toBe('100.205'); // mixed: the pair rule, what was heard is shown to the owner
    expect(plain('5,7 zł')).toBe('5.7');
    expect(plain('30%')).toBe('30');
    expect(plain('7,5 h')).toBe('7.5');
  });

  it('money: a zloty word is the decimal mark and a grosz word says nothing', () => {
    expect(plain('сто двадцать злотых пятьдесят грошей')).toBe('120.50');
    expect(plain('sto dwadzieścia złotych pięćdziesiąt groszy')).toBe('120.50');
    expect(plain('пять злотых')).toBe('5');
    expect(plain('двадцать процентов')).toBe('20');
    expect(plain('godzin osiem')).toBe('8');
  });
});

describe('lengths: the result is in metres', () => {
  it.each([
    ['три метра восемьдесят', '3.8'], ['trzy metry osiemdziesiąt', '3.8'], ['three meters eighty', '3.8'], ['3 m 80', '3.8'], ['3 м 80 см', '3.8'], ['три метри вісімдесят', '3.8'],
    ['три метра пять', '3.05'], ['два метра', '2'], ['метр двадцать', '1.2'], ['one meter twenty', '1.2'],
    ['двести пятьдесят сантиметров', '2.5'], ['dwieście pięćdziesiąt centymetrów', '2.5'], ['250 cm', '2.5'], ['250cm', '2.5'], ['250 см', '2.5'],
    ['двести пятьдесят', '2.5'], ['250', '2.5'], ['sto dwadzieścia', '1.2'], ['пятнадцать', '0.15'], ['пятьдесят', '0.5'],
    ['два', '2'], ['пять', '5'], ['девять', '9'],
    ['два пятьдесят', '2.50'], ['два семь', '2.7'], ['пять двадцать три', '5.23'], ['2 50', '2.50'], ['3,8', '3.8'], ['2,5 метра', '2.5'], ['пять точка двадцать три', '5.23'],
    ['триста миллиметров', '0.3'], ['dwa metry pięćdziesiąt centymetrów', '2.5'], ['2 m', '2'], ['3m80', '3.8'],
  ])('%s = %s m', (text, expected) => {
    expect(metres(text)).toBe(expected);
  });

  it('in the plain mode the units say nothing', () => {
    expect(plain('три метра восемьдесят')).toBe('3.80');
    expect(plain('250 см')).toBe('250');
  });
});

describe('what it does not take', () => {
  it.each(['', '   ', 'привет', 'hello world', 'пять абракадабра семь', 'dwa blabla trzy', 'пять сто', 'и', 'точка', 'сантиметр'])('"%s" is not a number', (text) => {
    // "и", "точка": a mark alone says nothing; "сантиметр" has no quantity
    expect(plain(text)).toBeNull();
    expect(metres(text)).toBeNull();
  });

  it('lets an unknown word stand at the edges (the owner said the name of the field) but not inside the number', () => {
    expect(plain('ширина пять точка два')).toBe('5.2');
    expect(plain('пять точка два метров')).toBe('5.2');
    expect(metres('wysokość dwa pięćdziesiąt')).toBe('2.50');
    expect(plain('пять и абракадабра два')).toBeNull();
  });

  it('refuses a number that cannot be a size or a sum', () => {
    expect(plain('1234567890123')).toBeNull();
  });
});

describe('alternatives and the table', () => {
  it('takes the first alternative that is a number', () => {
    expect(parseSpokenAlternatives(['piąty', 'pięć przecinek dwa', 'pięć'], 'plain')).toEqual({ text: 'pięć przecinek dwa', value: '5.2' });
    expect(parseSpokenAlternatives(['xyz', 'abc'], 'plain')).toBeNull();
    expect(parseSpokenAlternatives([], 'plain')).toBeNull();
  });

  it('normalizes capitals, diacritics and apostrophes the same way for the table and the text', () => {
    expect(normalizeSpeech("Pięć П'ЯТЬ Ёлка Йод")).toBe('piec пять елка иод');
  });
});
