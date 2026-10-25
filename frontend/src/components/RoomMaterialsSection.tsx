import { FormEvent, useCallback, useState } from 'react';
import { ApiError } from '../api/http';
import { createCalc, deleteCalc, fetchCalcs, updateCalc } from '../api/materials';
import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';
import type { CalcFields, DrywallParams, MaterialCalc, MaterialPackage, TileParams } from '../types/materials';
import { areaFromSides, buyWord, calcSummary, needWord, positiveDecimal } from '../utils/materialsFormat';
import { formatPlain, toInput } from '../utils/paymentFormat';
import { Ico } from './Ico';
import { fieldClass, labelClass, primaryButton, secondaryButton, segmentClass } from './paymentUi';
import { VoiceInput } from './VoiceInput';

/** The areas of the room that the server already counted (the card of the room shows them): the form offers them with one tap; nothing is counted here. */
export interface RoomAreas {
  floor: string | number | null;
  ceiling: string | number | null;
  walls: string | number | null;
  perimeter: string | number | null;
  height: string | number | null;
}

type Texts = { [K in keyof RoomAreas]: string | null };

/** The areas as the texts of the form fields. */
function asTexts(areas: RoomAreas): Texts {
  // the server counts a room to three places, the fields take two: the area offered is rounded to the place that the field takes
  const one = (value: string | number | null) => (value === null || value === undefined || Number.isNaN(Number(value)) ? null : Number(value).toFixed(2));
  return { floor: one(areas.floor), ceiling: one(areas.ceiling), walls: one(areas.walls), perimeter: one(areas.perimeter), height: one(areas.height) };
}

interface RoomMaterialsSectionProps {
  projectId: string;
  roomId: string;
  areas: RoomAreas;
}

const compactButton = 'w-full min-h-11 px-2 py-2 text-sm leading-tight rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium break-words hover:bg-slate-50 disabled:opacity-50';
const compactDanger = 'w-full min-h-11 px-2 py-2 text-sm leading-tight rounded-xl border border-red-200 bg-red-50 text-red-800 font-semibold break-words hover:bg-red-100 disabled:opacity-50';
const radioRow = 'w-full min-h-11 px-3 py-2 flex items-center gap-3 text-left text-sm font-medium text-slate-700 rounded-xl border pe-surface';
const chip = 'min-h-11 px-3 py-2 text-sm rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium break-words hover:bg-slate-50';

/**
 * V2-11 — the calculations of materials of a room (tile and drywall): the owner's data in, what to buy out (the server counts it by the owner's norms). Closed until opened, so a room's
 * screen asks the server for nothing it does not show. Online only.
 */
export function RoomMaterialsSection({ projectId, roomId, areas }: RoomMaterialsSectionProps) {
  const { t } = useI18n();
  const text = t.materials;
  const { offline } = useConnection();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<MaterialCalc[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [form, setForm] = useState<{ calc?: MaterialCalc } | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      setRows(await fetchCalcs(projectId, roomId));
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId, roomId]);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && rows === null) void load();
  };

  const remove = async (calc: MaterialCalc) => {
    if (busyId) return;
    setBusyId(calc.id);
    setMessage(null);
    try {
      await deleteCalc(projectId, roomId, calc.id);
      setConfirmId(null);
      setMessage({ kind: 'ok', text: text.deleted });
      await load();
    } catch {
      setMessage({ kind: 'error', text: text.save_error });
    } finally {
      setBusyId(null);
    }
  };

  const summary = (calc: MaterialCalc): string => calcSummary(calc, text);

  return (
    <section aria-label="room-materials-section" className="w-full min-w-0 max-w-full mt-5 space-y-3">
      <button
        type="button"
        aria-label="room-materials-toggle"
        aria-expanded={open}
        onClick={toggle}
        className="w-full min-h-11 px-4 py-2 flex flex-wrap items-center justify-between gap-x-3 text-left text-base font-bold text-slate-900 pe-card rounded-2xl shadow-sm"
      >
        <span className="break-words"><Ico>🧱</Ico>{text.room_title}</span>
        <span className="text-sm font-semibold text-blue-700">{open ? text.hide : text.show}</span>
      </button>
      {open && (
        <div aria-label="room-materials" className="space-y-3">
          <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>
          {loading && rows === null && <p className="text-sm text-slate-500 text-center py-3">{text.loading}</p>}
          {!loading && loadFailed && (
            <div className="space-y-2">
              <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
              <button type="button" aria-label="room-materials-retry" onClick={() => void load()} className={primaryButton}><Ico>🔄</Ico>{text.retry}</button>
            </div>
          )}
          {rows && (
            <>
              {form === null ? (
                <>
                  <button type="button" aria-label="material-calc-add" disabled={offline} onClick={() => { setMessage(null); setForm({}); }} className={primaryButton}>
                    <Ico>➕</Ico>{text.add}
                  </button>
                  {offline && <p aria-label="room-materials-offline" className="text-xs text-slate-500 break-words">{text.needs_connection}</p>}
                </>
              ) : (
                <CalcForm
                  key={form.calc?.id ?? 'new'}
                  projectId={projectId}
                  roomId={roomId}
                  calc={form.calc}
                  areas={areas}
                  onSaved={() => { setForm(null); setMessage({ kind: 'ok', text: text.saved }); void load(); }}
                  onCancel={() => setForm(null)}
                />
              )}
              {message && (
                <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-sm break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>{message.text}</p>
              )}
              {rows.length === 0 ? (
                <p aria-label="room-materials-empty" className="text-sm text-slate-500 text-center py-3">{text.empty}</p>
              ) : (
                <ul aria-label="material-calcs-list" className="space-y-2 min-w-0">
                  {rows.map((calc) => (
                    <li key={calc.id} aria-label={`material-calc-${calc.id}`} className="pe-card rounded-2xl p-3 shadow-sm space-y-2">
                      <div>
                        <p className="text-sm font-semibold text-slate-900 break-words">{calc.title ?? (calc.package === 'TILE' ? text.pkg_TILE : text.pkg_DRYWALL)}</p>
                        <p className="text-xs text-slate-600 break-words">{summary(calc)}</p>
                      </div>
                      <ul aria-label={`material-lines-${calc.id}`} className="divide-y divide-slate-100">
                        {calc.materials.map((line) => (
                          <li key={line.code} className="py-1.5 flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <p className="text-sm text-slate-900 break-words">{line.name}</p>
                              <p className="text-xs text-slate-500 break-words">{needWord(line, text)}</p>
                            </div>
                            <p className="shrink-0 text-sm font-bold text-slate-900 whitespace-nowrap">{buyWord(line, text)}</p>
                          </li>
                        ))}
                      </ul>
                      {confirmId !== calc.id ? (
                        <div className="grid grid-cols-2 gap-2">
                          <button type="button" aria-label={`material-calc-edit-${calc.id}`} disabled={offline} onClick={() => { setMessage(null); setForm({ calc }); }} className={compactButton}>
                            <Ico>✏️</Ico>{text.edit}
                          </button>
                          <button type="button" aria-label={`material-calc-delete-${calc.id}`} disabled={busyId === calc.id || offline} onClick={() => setConfirmId(calc.id)} className={compactButton}>
                            <Ico>🗑️</Ico>{text.delete}
                          </button>
                        </div>
                      ) : (
                        <div aria-label={`material-calc-confirm-${calc.id}`} className="space-y-2">
                          <p className="text-sm text-slate-800 break-words">{text.delete_confirm}</p>
                          <div className="grid grid-cols-2 gap-2">
                            <button type="button" aria-label={`material-calc-delete-yes-${calc.id}`} disabled={busyId === calc.id} onClick={() => void remove(calc)} className={compactDanger}>
                              <Ico>🗑️</Ico>{text.delete_yes}
                            </button>
                            <button type="button" aria-label={`material-calc-delete-no-${calc.id}`} onClick={() => setConfirmId(null)} className={compactButton}>
                              <Ico>✖️</Ico>{t.common.cancel}
                            </button>
                          </div>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

function CalcForm({
  projectId, roomId, calc, areas: rawAreas, onSaved, onCancel,
}: { projectId: string; roomId: string; calc?: MaterialCalc; areas: RoomAreas; onSaved: () => void; onCancel: () => void }) {
  const { t } = useI18n();
  const text = t.materials;
  const areas = asTexts(rawAreas);
  const p = calc?.params ?? {};
  const [pkg, setPkg] = useState<MaterialPackage>(calc?.package ?? 'TILE');
  const [title, setTitle] = useState(calc?.title ?? '');
  const [area, setArea] = useState(toInput(p.area_m2));
  // the area is given either directly or by the two sides of the surface: only one way at a time
  const [areaMode, setAreaMode] = useState<'AREA' | 'DIMS'>('AREA');
  const [sideLength, setSideLength] = useState('');
  const [sideWidth, setSideWidth] = useState('');
  // the tile
  const [length, setLength] = useState(toInput(p.length_cm));
  const [width, setWidth] = useState(toInput(p.width_cm));
  const [thickness, setThickness] = useState(toInput(p.thickness_mm ?? '8'));
  const [joint, setJoint] = useState(toInput(p.joint_mm ?? '3'));
  const [diagonal, setDiagonal] = useState(p.layout === 'DIAGONAL');
  const [waterproof, setWaterproof] = useState(p.waterproof ?? false);
  const [wpArea, setWpArea] = useState(toInput(p.waterproof_area_m2 ?? ''));
  const [tape, setTape] = useState(toInput(p.tape_m ?? ''));
  // the drywall
  const [ceiling, setCeiling] = useState(p.kind === 'CEILING');
  const [layers, setLayers] = useState<1 | 2>(p.layers === 2 ? 2 : 1);
  const [height, setHeight] = useState(toInput(p.height_m ?? areas.height ?? ''));
  const [perimeter, setPerimeter] = useState(toInput(p.perimeter_m ?? areas.perimeter ?? ''));
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const numberField = (id: string, value: string, set: (v: string) => void, label: string, placeholder?: string) => (
    <div>
      <label htmlFor={id} className={labelClass}>{label}</label>
      <VoiceInput name={id} mode="plain" onValue={(v) => set(v.replace('.', ','))}>
        <input id={id} aria-label={id} inputMode="decimal" autoComplete="off" value={value} placeholder={placeholder} onChange={(event) => set(event.target.value)} className={`${fieldClass} min-w-0 flex-1`} />
      </VoiceInput>
      {errors.includes(id) && <p role="alert" className="text-xs text-red-600 mt-1">{text[`err_${id.replace('material-', '')}` as keyof typeof text] as string}</p>}
    </div>
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const found: string[] = [];
    const need = (id: string, value: string | null) => {
      if (value === null) found.push(id);
      return value ?? '';
    };
    let areaValue: string;
    if (areaMode === 'AREA') areaValue = need('material-area', positiveDecimal(area, 2, 100000));
    else {
      const lengthOk = positiveDecimal(sideLength, 2, 1000) !== null;
      const widthOk = positiveDecimal(sideWidth, 2, 1000) !== null;
      if (!lengthOk) found.push('material-surface_length');
      if (!widthOk) found.push('material-surface_width');
      const product = lengthOk && widthOk ? areaFromSides(sideLength, sideWidth) : null;
      if (lengthOk && widthOk && product === null) found.push('material-area');
      areaValue = product ?? '';
    }
    let fields: CalcFields;
    if (pkg === 'TILE') {
      const params: TileParams = {
        area_m2: areaValue,
        length_cm: need('material-length', positiveDecimal(length, 1, 1000)),
        width_cm: need('material-width', positiveDecimal(width, 1, 1000)),
        thickness_mm: need('material-thickness', positiveDecimal(thickness, 1, 100)),
        joint_mm: need('material-joint', positiveDecimal(joint, 1, 100)),
        layout: diagonal ? 'DIAGONAL' : 'STRAIGHT',
        waterproof,
        waterproof_area_m2: null,
        tape_m: null,
      };
      if (waterproof && wpArea.trim() !== '') params.waterproof_area_m2 = need('material-wp_area', positiveDecimal(wpArea, 2, 100000));
      if (waterproof && tape.trim() !== '') params.tape_m = need('material-tape', positiveDecimal(tape, 2, 100000));
      fields = { package: 'TILE', title: title.trim() !== '' ? title.trim() : null, params };
    } else {
      const params: DrywallParams = { kind: ceiling ? 'CEILING' : 'WALL', area_m2: areaValue, layers, height_m: null, perimeter_m: null };
      if (ceiling) params.perimeter_m = need('material-perimeter', positiveDecimal(perimeter, 2, 100000));
      else params.height_m = need('material-height', positiveDecimal(height, 2, 100000));
      fields = { package: 'DRYWALL', title: title.trim() !== '' ? title.trim() : null, params };
    }
    setErrors(found);
    if (found.length > 0) return;
    setBusy(true);
    setFailure(null);
    try {
      if (calc) await updateCalc(projectId, roomId, calc.id, { title: fields.title, params: fields.params });
      else await createCalc(projectId, roomId, fields);
      onSaved();
    } catch (err) {
      setFailure(err instanceof ApiError ? text.save_error : text.save_error);
      setBusy(false);
    }
  };

  const quick = (label: string, value: string | null) =>
    value === null || value === '' ? null : (
      <button key={label} type="button" aria-label={`material-use-${label}`} onClick={() => setArea(toInput(value))} className={chip}>
        {label}
      </button>
    );
  const areaModes: ['AREA' | 'DIMS', string][] = [['AREA', text.area_mode_area], ['DIMS', text.area_mode_dims]];
  const sidesArea = areaFromSides(sideLength, sideWidth);
  const chips = [
    quick(text.use_floor.replace('{v}', formatPlain(areas.floor)), pkg === 'TILE' ? areas.floor : null),
    quick(text.use_walls.replace('{v}', formatPlain(areas.walls)), areas.walls),
    quick(text.use_ceiling.replace('{v}', formatPlain(areas.ceiling)), areas.ceiling),
  ].filter(Boolean);

  return (
    <form aria-label="material-calc-form" onSubmit={submit} noValidate className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <h3 className="text-sm font-semibold text-slate-900 break-words">{calc ? text.edit_title : text.add_title}</h3>
      {!calc && (
        <div>
          <span className={labelClass}>{text.package_label}</span>
          <div className="flex gap-2">
            <button type="button" aria-label="material-package-TILE" aria-pressed={pkg === 'TILE'} onClick={() => setPkg('TILE')} className={segmentClass(pkg === 'TILE')}>{text.pkg_TILE}</button>
            <button type="button" aria-label="material-package-DRYWALL" aria-pressed={pkg === 'DRYWALL'} onClick={() => setPkg('DRYWALL')} className={segmentClass(pkg === 'DRYWALL')}>{text.pkg_DRYWALL}</button>
          </div>
        </div>
      )}
      <div>
        <label htmlFor="material-title" className={labelClass}>{text.title_label}</label>
        <input id="material-title" aria-label="material-title" maxLength={120} value={title} placeholder={text.title_placeholder} onChange={(event) => setTitle(event.target.value)} className={fieldClass} />
      </div>
      {pkg === 'DRYWALL' && (
        <div>
          <span className={labelClass}>{text.kind_label}</span>
          <div className="flex gap-2">
            <button type="button" aria-label="material-kind-WALL" aria-pressed={!ceiling} onClick={() => setCeiling(false)} className={segmentClass(!ceiling)}>{text.kind_WALL}</button>
            <button type="button" aria-label="material-kind-CEILING" aria-pressed={ceiling} onClick={() => setCeiling(true)} className={segmentClass(ceiling)}>{text.kind_CEILING}</button>
          </div>
        </div>
      )}
      <div>
        <span id="material-area-mode-label" className={labelClass}>{text.area_mode_label}</span>
        <div role="radiogroup" aria-labelledby="material-area-mode-label" className="flex flex-col gap-2">
          {areaModes.map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={areaMode === mode}
              aria-label={`material-area-mode-${mode}`}
              onClick={() => { setAreaMode(mode); setErrors([]); }}
              className={`${radioRow} ${areaMode === mode ? 'border-blue-600' : 'border-slate-200'}`}
            >
              <span aria-hidden="true" className={`shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center ${areaMode === mode ? 'border-blue-600' : 'border-slate-400'}`}>
                {areaMode === mode && <span className="w-2.5 h-2.5 rounded-full bg-blue-600" />}
              </span>
              <span className="min-w-0 break-words">{label}</span>
            </button>
          ))}
        </div>
      </div>
      {areaMode === 'AREA' ? (
        <>
          {numberField('material-area', area, setArea, text.area_label)}
          {chips.length > 0 && <div aria-label="material-area-chips" className="flex flex-wrap gap-2">{chips}</div>}
        </>
      ) : (
        <>
          <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3">
            {numberField('material-surface_length', sideLength, setSideLength, text.surface_length)}
            {numberField('material-surface_width', sideWidth, setSideWidth, text.surface_width)}
          </div>
          {sidesArea !== null && <p aria-label="material-area-result" className="text-sm font-semibold text-slate-900 break-words">{text.area_result.replace('{v}', formatPlain(sidesArea))}</p>}
          {errors.includes('material-area') && <p role="alert" className="text-xs text-red-600">{text.err_area}</p>}
        </>
      )}
      {pkg === 'TILE' ? (
        <>
          <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3">
            {numberField('material-length', length, setLength, text.tile_length, '30')}
            {numberField('material-width', width, setWidth, text.tile_width, '60')}
            {numberField('material-thickness', thickness, setThickness, text.thickness)}
            {numberField('material-joint', joint, setJoint, text.joint)}
          </div>
          <div>
            <span className={labelClass}>{text.layout_label}</span>
            <div className="flex gap-2">
              <button type="button" aria-label="material-layout-STRAIGHT" aria-pressed={!diagonal} onClick={() => setDiagonal(false)} className={segmentClass(!diagonal)}>{text.layout_STRAIGHT}</button>
              <button type="button" aria-label="material-layout-DIAGONAL" aria-pressed={diagonal} onClick={() => setDiagonal(true)} className={segmentClass(diagonal)}>{text.layout_DIAGONAL}</button>
            </div>
          </div>
          <div>
            <span className={labelClass}>{text.waterproof_label}</span>
            <div className="flex gap-2">
              <button type="button" aria-label="material-waterproof-off" aria-pressed={!waterproof} onClick={() => setWaterproof(false)} className={segmentClass(!waterproof)}>{text.waterproof_off}</button>
              <button type="button" aria-label="material-waterproof-on" aria-pressed={waterproof} onClick={() => setWaterproof(true)} className={segmentClass(waterproof)}>{text.waterproof_on}</button>
            </div>
          </div>
          {waterproof && (
            <>
              {numberField('material-wp_area', wpArea, setWpArea, text.wp_area)}
              {numberField('material-tape', tape, setTape, text.tape)}
              {areas.perimeter && (
                <button type="button" aria-label="material-use-perimeter" onClick={() => setTape(toInput(areas.perimeter))} className={chip}>
                  {text.use_perimeter.replace('{v}', formatPlain(areas.perimeter))}
                </button>
              )}
            </>
          )}
        </>
      ) : (
        <>
          <div>
            <span className={labelClass}>{text.layers_label}</span>
            <div className="flex gap-2">
              <button type="button" aria-label="material-layers-1" aria-pressed={layers === 1} onClick={() => setLayers(1)} className={segmentClass(layers === 1)}>{text.layers_n.replace('{n}', '1')}</button>
              <button type="button" aria-label="material-layers-2" aria-pressed={layers === 2} onClick={() => setLayers(2)} className={segmentClass(layers === 2)}>{text.layers_n.replace('{n}', '2')}</button>
            </div>
          </div>
          {ceiling ? numberField('material-perimeter', perimeter, setPerimeter, text.perimeter_label) : numberField('material-height', height, setHeight, text.height_label)}
        </>
      )}
      {failure && <p role="alert" className="text-sm text-red-600 break-words">{failure}</p>}
      <div className="flex flex-col gap-2">
        <button type="submit" aria-label="material-calc-save" disabled={busy} className={primaryButton}>
          <Ico>{busy ? '⏳' : '💾'}</Ico>{busy ? t.common.saving : t.common.save}
        </button>
        <button type="button" aria-label="material-calc-cancel" onClick={onCancel} className={secondaryButton}>
          <Ico>✖️</Ico>{t.common.cancel}
        </button>
      </div>
    </form>
  );
}
