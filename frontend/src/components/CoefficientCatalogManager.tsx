import React, { useEffect, useState } from 'react';
import {
  archiveCoefficientGroup,
  archiveCoefficientOption,
  createCoefficientGroup,
  createCoefficientOption,
  fetchCoefficientGroups,
  restoreCoefficientGroup,
  restoreCoefficientOption,
  updateCoefficientGroup,
  updateCoefficientOption,
} from '../api/coefficients';
import { useI18n } from '../hooks/useI18n';
import { CoefficientGroupRead, CoefficientOptionRead } from '../types/coefficient';
import { formatPercentageDisplay } from '../utils/coefficientCalculations';

export const CoefficientCatalogManager: React.FC = () => {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<'active' | 'archived'>('active');
  const [groups, setGroups] = useState<CoefficientGroupRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Group creation form modal state
  const [isAddGroupOpen, setIsAddGroupOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [savingGroup, setSavingGroup] = useState(false);

  // Option creation modal state
  const [addingOptionGroupId, setAddingOptionGroupId] = useState<string | null>(null);
  const [newOptionName, setNewOptionName] = useState('');
  const [newOptionPercentage, setNewOptionPercentage] = useState('');
  const [newOptionIsBase, setNewOptionIsBase] = useState(false);
  const [savingOption, setSavingOption] = useState(false);

  // Editing state for group
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [editGroupName, setEditGroupName] = useState('');

  // Editing state for option
  const [editingOption, setEditingOption] = useState<CoefficientOptionRead | null>(null);
  const [editOptionName, setEditOptionName] = useState('');
  const [editOptionPercentage, setEditOptionPercentage] = useState('');
  const [editOptionIsBase, setEditOptionIsBase] = useState(false);

  const loadData = () => {
    setLoading(true);
    setError(null);
    fetchCoefficientGroups({
      archived: activeTab,
      include_archived_options: true,
    })
      .then((res) => {
        setGroups(res.items);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : t.coefficients.error_load);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, [activeTab]);

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupName.trim()) return;
    setSavingGroup(true);
    setError(null);
    try {
      await createCoefficientGroup({ display_name: newGroupName.trim() });
      setNewGroupName('');
      setIsAddGroupOpen(false);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.coefficients.error_save);
    } finally {
      setSavingGroup(false);
    }
  };

  const handleUpdateGroup = async (groupId: string) => {
    if (!editGroupName.trim()) return;
    try {
      await updateCoefficientGroup(groupId, { display_name: editGroupName.trim() });
      setEditingGroupId(null);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.coefficients.error_save);
    }
  };

  const handleArchiveGroup = async (groupId: string) => {
    try {
      await archiveCoefficientGroup(groupId);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.coefficients.error_save);
    }
  };

  const handleRestoreGroup = async (groupId: string) => {
    try {
      await restoreCoefficientGroup(groupId);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.coefficients.error_save);
    }
  };

  const handleCreateOption = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addingOptionGroupId || !newOptionName.trim() || !newOptionPercentage.trim()) return;
    setSavingOption(true);
    setError(null);
    try {
      await createCoefficientOption(addingOptionGroupId, {
        display_name: newOptionName.trim(),
        percentage: newOptionPercentage.trim().replace(',', '.'),
        is_base: newOptionIsBase,
      });
      setAddingOptionGroupId(null);
      setNewOptionName('');
      setNewOptionPercentage('');
      setNewOptionIsBase(false);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.coefficients.error_save);
    } finally {
      setSavingOption(false);
    }
  };

  const handleUpdateOption = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingOption || !editOptionName.trim() || !editOptionPercentage.trim()) return;
    try {
      await updateCoefficientOption(editingOption.id, {
        display_name: editOptionName.trim(),
        percentage: editOptionPercentage.trim().replace(',', '.'),
        is_base: editOptionIsBase,
      });
      setEditingOption(null);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.coefficients.error_save);
    }
  };

  const handleArchiveOption = async (optionId: string) => {
    try {
      await archiveCoefficientOption(optionId);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.coefficients.error_save);
    }
  };

  const handleRestoreOption = async (optionId: string) => {
    try {
      await restoreCoefficientOption(optionId);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.coefficients.error_save);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top action bar: filter tabs & add group */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-slate-200 p-1 bg-slate-100">
          <button
            type="button"
            onClick={() => setActiveTab('active')}
            className={`min-h-[44px] px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
              activeTab === 'active'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {t.coefficients.active_tab}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('archived')}
            className={`min-h-[44px] px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
              activeTab === 'archived'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {t.coefficients.archived_tab}
          </button>
        </div>

        {activeTab === 'active' && (
          <button
            type="button"
            onClick={() => setIsAddGroupOpen(true)}
            className="min-h-[44px] px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 active:bg-blue-800"
          >
            {t.coefficients.add_group}
          </button>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && (
        <div className="py-8 text-center text-sm text-slate-500">
          {t.coefficients.loading}
        </div>
      )}

      {!loading && groups.length === 0 && (
        <div className="py-8 text-center text-sm text-slate-500 bg-white rounded-xl border border-slate-200 p-6">
          {t.coefficients.no_groups}
        </div>
      )}

      {/* Groups List */}
      {!loading &&
        groups.map((group) => {
          const isEditing = editingGroupId === group.id;

          return (
            <div
              key={group.id}
              className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3"
            >
              {/* Group header */}
              <div className="flex flex-col gap-1 border-b border-slate-100 pb-2">
                <div className="flex-1 min-w-0">
                  {isEditing ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        type="text"
                        value={editGroupName}
                        onChange={(e) => setEditGroupName(e.target.value)}
                        className="min-w-0 flex-1 basis-40 min-h-[44px] px-2 py-1 border border-slate-300 rounded text-sm font-semibold"
                        autoFocus
                      />
                      <button
                        type="button"
                        onClick={() => handleUpdateGroup(group.id)}
                        className="min-h-[44px] px-3 py-1 bg-blue-600 text-white rounded text-xs font-semibold"
                      >
                        {t.coefficients.save}
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingGroupId(null)}
                        className="min-h-[44px] px-2 py-1 text-slate-600 hover:text-slate-800 text-xs"
                      >
                        {t.coefficients.cancel}
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="min-w-0 text-base font-bold text-slate-900 break-words">
                        {group.display_name || group.code}
                      </h3>
                      {group.is_archived && (
                        <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
                          {t.coefficients.archived_badge}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {!isEditing && (
                  <div className="flex flex-wrap items-center gap-1">
                    {!group.is_archived && (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingGroupId(group.id);
                          setEditGroupName(group.display_name || '');
                        }}
                        className="min-h-[44px] px-2 py-1 text-xs text-slate-600 hover:text-blue-600"
                      >
                        {t.coefficients.edit}
                      </button>
                    )}
                    {group.is_archived ? (
                      <button
                        type="button"
                        onClick={() => handleRestoreGroup(group.id)}
                        className="min-h-[44px] px-2 py-1 text-xs font-medium text-emerald-600 hover:text-emerald-700"
                      >
                        {t.coefficients.restore}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleArchiveGroup(group.id)}
                        className="min-h-[44px] px-2 py-1 text-xs text-slate-500 hover:text-red-600"
                      >
                        {t.coefficients.archive}
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Options list inside group */}
              <div className="space-y-2">
                {group.options.map((opt) => (
                  <div
                    key={opt.id}
                    className="flex flex-col p-2.5 rounded-lg border border-slate-100 bg-slate-50 text-sm gap-1"
                  >
                    <div className="flex flex-wrap items-center gap-2 min-w-0">
                      <span className="min-w-0 font-medium text-slate-800 break-words">
                        {opt.display_name || opt.code}
                      </span>
                      {opt.is_base && (
                        <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-800">
                          {t.coefficients.base_badge}
                        </span>
                      )}
                      {opt.is_archived && (
                        <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
                          {t.coefficients.archived_badge}
                        </span>
                      )}
                      <span className="ml-auto shrink-0 font-mono text-xs font-bold text-slate-700">
                        {formatPercentageDisplay(opt.percentage)}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {!opt.is_archived && !group.is_archived && (
                        <button
                          type="button"
                          onClick={() => {
                            setEditingOption(opt);
                            setEditOptionName(opt.display_name || '');
                            setEditOptionPercentage(opt.percentage);
                            setEditOptionIsBase(opt.is_base);
                          }}
                          className="min-h-[44px] px-2 text-xs text-slate-600 hover:text-blue-600"
                        >
                          {t.coefficients.edit}
                        </button>
                      )}
                      {opt.is_archived ? (
                        <button
                          type="button"
                          onClick={() => handleRestoreOption(opt.id)}
                          className="min-h-[44px] px-2 text-xs font-medium text-emerald-600 hover:text-emerald-700"
                        >
                          {t.coefficients.restore}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleArchiveOption(opt.id)}
                          className="min-h-[44px] px-2 text-xs text-slate-500 hover:text-red-600"
                        >
                          {t.coefficients.archive}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Add option button */}
              {!group.is_archived && (
                <button
                  type="button"
                  onClick={() => {
                    setAddingOptionGroupId(group.id);
                    setNewOptionName('');
                    setNewOptionPercentage('');
                    setNewOptionIsBase(false);
                  }}
                  className="w-full min-h-[44px] px-3 py-2 border border-dashed border-slate-300 hover:border-blue-500 hover:text-blue-600 text-slate-600 rounded-lg text-xs font-semibold flex items-center justify-center gap-1 transition-colors"
                >
                  {t.coefficients.add_option}
                </button>
              )}
            </div>
          );
        })}

      {/* Add Group Modal */}
      {isAddGroupOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl overflow-hidden p-4 space-y-4">
            <h3 className="text-base font-bold text-slate-900">
              {t.coefficients.add_group}
            </h3>
            <form onSubmit={handleCreateGroup} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t.coefficients.group_name}
                </label>
                <input
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder={t.coefficients.group_name_placeholder}
                  className="w-full min-h-[44px] px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  required
                  autoFocus
                />
              </div>
              <div className="flex items-center gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsAddGroupOpen(false)}
                  className="flex-1 min-h-[44px] px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50"
                >
                  {t.coefficients.cancel}
                </button>
                <button
                  type="submit"
                  disabled={savingGroup || !newGroupName.trim()}
                  className="flex-1 min-h-[44px] px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50"
                >
                  {savingGroup ? t.coefficients.saving : t.coefficients.save}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Option Modal */}
      {addingOptionGroupId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl overflow-hidden p-4 space-y-4">
            <h3 className="text-base font-bold text-slate-900">
              {t.coefficients.add_option}
            </h3>
            <form onSubmit={handleCreateOption} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t.coefficients.option_name}
                </label>
                <input
                  type="text"
                  value={newOptionName}
                  onChange={(e) => setNewOptionName(e.target.value)}
                  placeholder={t.coefficients.option_name_placeholder}
                  className="w-full min-h-[44px] px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t.coefficients.percentage}
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={newOptionPercentage}
                  onChange={(e) => setNewOptionPercentage(e.target.value)}
                  placeholder="np. 20 lub -10"
                  className="w-full min-h-[44px] px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  required
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="new-option-base"
                  checked={newOptionIsBase}
                  onChange={(e) => setNewOptionIsBase(e.target.checked)}
                  className="h-4 w-4 text-blue-600 rounded focus:ring-blue-500"
                />
                <label htmlFor="new-option-base" className="text-sm text-slate-700 cursor-pointer">
                  {t.coefficients.is_base_label}
                </label>
              </div>
              <div className="flex items-center gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setAddingOptionGroupId(null)}
                  className="flex-1 min-h-[44px] px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50"
                >
                  {t.coefficients.cancel}
                </button>
                <button
                  type="submit"
                  disabled={savingOption || !newOptionName.trim() || !newOptionPercentage.trim()}
                  className="flex-1 min-h-[44px] px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50"
                >
                  {savingOption ? t.coefficients.saving : t.coefficients.save}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Option Modal */}
      {editingOption && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl overflow-hidden p-4 space-y-4">
            <h3 className="text-base font-bold text-slate-900">
              {t.coefficients.edit}
            </h3>
            <form onSubmit={handleUpdateOption} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t.coefficients.option_name}
                </label>
                <input
                  type="text"
                  value={editOptionName}
                  onChange={(e) => setEditOptionName(e.target.value)}
                  className="w-full min-h-[44px] px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t.coefficients.percentage}
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={editOptionPercentage}
                  onChange={(e) => setEditOptionPercentage(e.target.value)}
                  className="w-full min-h-[44px] px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  required
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="edit-option-base"
                  checked={editOptionIsBase}
                  onChange={(e) => setEditOptionIsBase(e.target.checked)}
                  className="h-4 w-4 text-blue-600 rounded focus:ring-blue-500"
                />
                <label htmlFor="edit-option-base" className="text-sm text-slate-700 cursor-pointer">
                  {t.coefficients.is_base_label}
                </label>
              </div>
              <div className="flex items-center gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingOption(null)}
                  className="flex-1 min-h-[44px] px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50"
                >
                  {t.coefficients.cancel}
                </button>
                <button
                  type="submit"
                  disabled={!editOptionName.trim() || !editOptionPercentage.trim()}
                  className="flex-1 min-h-[44px] px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50"
                >
                  {t.coefficients.save}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
