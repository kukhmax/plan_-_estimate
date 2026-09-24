import { describe, expect, it } from 'vitest';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import {
  coefficientGroupDescription,
  coefficientGroupName,
  coefficientOptionDescription,
  coefficientOptionName,
} from './coefficientLabels';

const canonical = pl.coefficients.builtin.WYSOKOSC_PRACY;
const canonicalOption = canonical.options.PODWYZSZONA;

const untouchedGroup = {
  code: 'WYSOKOSC_PRACY',
  display_name: canonical.name,
  description: canonical.description,
};
const untouchedOption = {
  code: 'PODWYZSZONA',
  display_name: canonicalOption.name,
  description: canonicalOption.description,
};

describe('coefficientLabels (Stage 12G built-in localization)', () => {
  it('shows an untouched built-in group in the active locale', () => {
    expect(coefficientGroupName(untouchedGroup, pl)).toBe('Wysokość pracy');
    expect(coefficientGroupName(untouchedGroup, ru)).toBe('Высота работ');
    expect(coefficientGroupDescription(untouchedGroup, ru)).toBe(
      ru.coefficients.builtin.WYSOKOSC_PRACY.description,
    );
    expect(coefficientGroupDescription(untouchedGroup, pl)).toBe(canonical.description);
  });

  it('shows an untouched built-in option in the active locale, keyed by group code', () => {
    expect(coefficientOptionName('WYSOKOSC_PRACY', untouchedOption, pl)).toBe('Podwyższona');
    expect(coefficientOptionName('WYSOKOSC_PRACY', untouchedOption, ru)).toBe('Повышенная');
    expect(coefficientOptionDescription('WYSOKOSC_PRACY', untouchedOption, ru)).toBe(
      ru.coefficients.builtin.WYSOKOSC_PRACY.options.PODWYZSZONA.description,
    );
    // Same option code in another group resolves through that group.
    const standard = {
      code: 'STANDARDOWA',
      display_name: 'Standardowa',
      description: pl.coefficients.builtin.ZLOZONOSC_POWIERZCHNI.options.STANDARDOWA.description,
    };
    expect(coefficientOptionDescription('ZLOZONOSC_POWIERZCHNI', standard, ru)).toBe(
      ru.coefficients.builtin.ZLOZONOSC_POWIERZCHNI.options.STANDARDOWA.description,
    );
  });

  it('never hides an owner-customized built-in group name or description', () => {
    const edited = { ...untouchedGroup, display_name: 'Moja wysokość', description: 'Mój opis' };
    expect(coefficientGroupName(edited, ru)).toBe('Moja wysokość');
    expect(coefficientGroupDescription(edited, ru)).toBe('Mój opis');
  });

  it('never hides an owner-customized built-in option name or description', () => {
    const edited = { ...untouchedOption, display_name: 'Na drabinie', description: 'Własny opis' };
    expect(coefficientOptionName('WYSOKOSC_PRACY', edited, ru)).toBe('Na drabinie');
    expect(coefficientOptionDescription('WYSOKOSC_PRACY', edited, ru)).toBe('Własny opis');
    // Customizing only the name still translates an untouched description.
    const nameOnly = { ...untouchedOption, display_name: 'Na drabinie' };
    expect(coefficientOptionName('WYSOKOSC_PRACY', nameOnly, ru)).toBe('Na drabinie');
    expect(coefficientOptionDescription('WYSOKOSC_PRACY', nameOnly, ru)).toBe(
      ru.coefficients.builtin.WYSOKOSC_PRACY.options.PODWYZSZONA.description,
    );
  });

  it('keeps an owner-cleared built-in description cleared', () => {
    expect(coefficientGroupDescription({ ...untouchedGroup, description: null }, ru)).toBeNull();
  });

  it('shows owner-created groups and options exactly as stored', () => {
    const custom = { code: 'CUSTOM_ABC', display_name: 'Moja grupa', description: 'Opis' };
    expect(coefficientGroupName(custom, ru)).toBe('Moja grupa');
    expect(coefficientGroupDescription(custom, ru)).toBe('Opis');
    const customOption = { code: 'CUSTOM_DEF', display_name: 'Opcja', description: null };
    expect(coefficientOptionName('WYSOKOSC_PRACY', customOption, ru)).toBe('Opcja');
    expect(coefficientOptionName('CUSTOM_ABC', customOption, ru)).toBe('Opcja');
  });

  it('falls back to the code when no name is stored', () => {
    expect(coefficientGroupName({ code: 'CUSTOM_X', display_name: null, description: null }, ru)).toBe(
      'CUSTOM_X',
    );
  });
});
