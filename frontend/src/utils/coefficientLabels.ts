/**
 * Stage 12G: localized presentation of the program-provided coefficient
 * catalog.
 *
 * Built-in groups/options are persisted with canonical Polish text (the
 * backend seed, `app/domain/data/price_coefficients.py`), mirrored exactly in
 * `pl.json` under `coefficients.builtin`. A stored value is shown translated
 * only while it still equals that canonical program text for its stable
 * group/option code; any other stored value (an owner edit, a cleared
 * description, an owner-created group) is shown exactly as stored. Estimate
 * snapshots are never touched by this module.
 */
import pl from '../locales/pl.json';

interface BuiltinEntry {
  name: string;
  description: string;
}

interface BuiltinGroupEntry extends BuiltinEntry {
  options: Record<string, BuiltinEntry>;
}

type BuiltinCatalog = Record<string, BuiltinGroupEntry>;

const CANONICAL: BuiltinCatalog = pl.coefficients.builtin;

interface LabelledGroup {
  code: string;
  display_name: string | null;
  description: string | null;
}

interface LabelledOption {
  code: string;
  display_name: string | null;
  description: string | null;
}

function localized(
  stored: string | null,
  canonical: string | undefined,
  translated: string | undefined,
): string | null {
  if (stored !== null && canonical !== undefined && stored === canonical) {
    return translated ?? stored;
  }
  return stored;
}

function localeCatalog(t: { coefficients: { builtin: unknown } }): BuiltinCatalog {
  return t.coefficients.builtin as BuiltinCatalog;
}

export function coefficientGroupName(
  group: LabelledGroup,
  t: { coefficients: { builtin: unknown } },
): string {
  const translated = localized(
    group.display_name,
    CANONICAL[group.code]?.name,
    localeCatalog(t)[group.code]?.name,
  );
  return translated || group.code;
}

export function coefficientGroupDescription(
  group: LabelledGroup,
  t: { coefficients: { builtin: unknown } },
): string | null {
  return localized(
    group.description,
    CANONICAL[group.code]?.description,
    localeCatalog(t)[group.code]?.description,
  );
}

export function coefficientOptionName(
  groupCode: string,
  option: LabelledOption,
  t: { coefficients: { builtin: unknown } },
): string {
  const translated = localized(
    option.display_name,
    CANONICAL[groupCode]?.options[option.code]?.name,
    localeCatalog(t)[groupCode]?.options[option.code]?.name,
  );
  return translated || option.code;
}

export function coefficientOptionDescription(
  groupCode: string,
  option: LabelledOption,
  t: { coefficients: { builtin: unknown } },
): string | null {
  return localized(
    option.description,
    CANONICAL[groupCode]?.options[option.code]?.description,
    localeCatalog(t)[groupCode]?.options[option.code]?.description,
  );
}
