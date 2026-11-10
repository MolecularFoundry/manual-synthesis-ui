import { useState, useEffect } from 'react';
import { recordStep, editStepRecord, getStepRecord, uploadStepFiles } from '../../services/api';

const ALLOWED_PARENTS = { create_chiplets: ['wafer'], create_chips: ['wafer', 'chiplet'] };
const CHILD_SUFFIX = { create_chiplets: 'CL', create_chips: 'C' };
const SUBSTEP_FIELDS = [
  ['params', 'Parameters'], ['temp', 'Temp'], ['time', 'Time'],
  ['tool', 'Tool'], ['specs', 'Tool specs'], ['comment', 'Comment'],
];
const today = () => new Date().toISOString().split('T')[0];

const childNames = (parentName, suffix, count) =>
  Array.from({ length: count }, (_, i) => `${parentName}_${suffix}${String(i + 1).padStart(2, '0')}`);

const errorText = (err, fallback) => err.response?.data?.detail || fallback;

// `record` set = view/edit an existing entry; otherwise record a new one.
const StepForm = ({ step, record, traveler, project, userInfo, earlierPending = [], onClose, onRecorded }) => {
  const editing = Boolean(record);
  const { units, wafer, template_id: templateId } = traveler;
  const action = editing ? null : step.action;
  const leafUnits = units.filter((u) => u.is_leaf);
  const parentCandidates = action
    ? leafUnits.filter((u) => ALLOWED_PARENTS[action].includes(u.sample_type))
    : [];
  const showParams = !editing || record.status === 'done';

  const [params, setParams] = useState(() =>
    Object.fromEntries(step.parameters.map((p) => {
      const value = editing ? record.parameters?.[p.key] : p.default;
      return [p.key, value ?? ''];
    }))
  );
  const [substeps, setSubsteps] = useState(() => {
    const saved = editing && record.substeps?.length === step.substeps.length ? record.substeps : step.substeps;
    return saved.map((s) => ({ ...s }));
  });
  const [date, setDate] = useState(editing ? record.step_date || today() : today());
  const [comments, setComments] = useState(editing ? record.comments || '' : '');
  const [targets, setTargets] = useState(
    action ? parentCandidates.map((u) => u.unique_id) : leafUnits.map((u) => u.unique_id)
  );
  const [children, setChildren] = useState(() =>
    Object.fromEntries(parentCandidates.map((u) => [u.unique_id, childNames(u.sample_name, CHILD_SUFFIX[action], 4)]))
  );
  const [newFiles, setNewFiles] = useState([]);
  const [attached, setAttached] = useState(null);
  const [error, setError] = useState('');
  const [problems, setProblems] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!editing) return;
    getStepRecord(record.dataset_id)
      .then((res) => setAttached(res.files))
      .catch(() => setAttached([]));
  }, [editing, record]);

  const toggleTarget = (id) =>
    setTargets((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));

  const setChildCount = (parent, count) =>
    setChildren((prev) => ({
      ...prev,
      [parent.unique_id]: childNames(parent.sample_name, CHILD_SUFFIX[action], Math.max(0, count)),
    }));

  const setChildName = (parentId, idx, name) =>
    setChildren((prev) => ({ ...prev, [parentId]: prev[parentId].map((n, i) => (i === idx ? name : n)) }));

  const setSubstepField = (idx, field, value) =>
    setSubsteps((prev) => prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));

  const uploadFiles = async (datasetId) => {
    if (!newFiles.length) return [];
    try {
      return (await uploadStepFiles(datasetId, newFiles)).errors;
    } catch (err) {
      return [errorText(err, 'File upload failed')];
    }
  };

  const submit = async (status) => {
    setLoading(true);
    setError('');
    try {
      let datasetId;
      let issues = [];
      if (editing) {
        await editStepRecord(record.dataset_id, {
          orcid: userInfo.orcid,
          operator: userInfo.name,
          step_date: date,
          parameters: showParams ? params : {},
          substeps,
          comments,
        });
        datasetId = record.dataset_id;
      } else {
        const res = await recordStep({
          template_id: templateId,
          step_id: step.id,
          wafer_id: wafer.unique_id,
          project,
          orcid: userInfo.orcid,
          operator: userInfo.name,
          target_ids: targets,
          status,
          step_date: date,
          parameters: status === 'done' ? params : {},
          substeps,
          comments,
          new_children: action && status === 'done'
            ? Object.fromEntries(targets.map((t) => [t, children[t] || []]))
            : {},
        });
        datasetId = res.dataset_id;
        issues = res.errors;
      }
      issues = [...issues, ...(await uploadFiles(datasetId))];
      if (issues.length) {
        setProblems(issues);
      } else {
        await onRecorded();
      }
    } catch (err) {
      setError(errorText(err, editing ? 'Failed to save changes' : 'Failed to record step'));
    } finally {
      setLoading(false);
    }
  };

  const selectable = action ? parentCandidates : units;
  const unitName = Object.fromEntries(units.map((u) => [u.unique_id, u.sample_name]));

  return (
    <div className="modal-backdrop">
      <div className="modal-panel">
        <div className="traveler-header">
          <h3>{step.label} — {step.name}{editing ? ' (view / edit)' : ''}</h3>
          <button className="btn btn-secondary btn-small" onClick={onClose} disabled={loading}>Close</button>
        </div>
        {step.tool && <p className="muted">Tool: {step.tool}</p>}

        {editing && (
          <p className="muted">
            {record.status === 'skipped' ? 'Skipped' : 'Recorded'} by {record.operator || 'unknown'}
            {' · '}applies to {record.unit_ids.map((id) => unitName[id] || id).join(', ')}
            {record.edited_by && ` · last edited by ${record.edited_by}`}
          </p>
        )}

        {!editing && earlierPending.length > 0 && (
          <div className="warning-message">
            Earlier required steps are still pending: {earlierPending.map((s) => s.label).join(', ')}.
            You can still record this step.
          </div>
        )}

        {showParams && step.parameters.length > 0 && (
          <div className="param-grid">
            {step.parameters.map((p) => (
              <div className="form-group" key={p.key}>
                <label>{p.label}{p.unit ? ` (${p.unit})` : ''}</label>
                <input
                  type={p.type === 'number' ? 'number' : 'text'}
                  step="any"
                  value={params[p.key]}
                  onChange={(e) => setParams({ ...params, [p.key]: e.target.value })}
                />
              </div>
            ))}
          </div>
        )}

        {showParams && substeps.length > 0 && (
          <details className="substeps" open={editing}>
            <summary>Procedure ({substeps.length} sub-steps, all editable)</summary>
            <div className="substep-table-wrap">
              <table className="substep-table">
                <thead>
                  <tr><th>Process</th>{SUBSTEP_FIELDS.map(([, label]) => <th key={label}>{label}</th>)}</tr>
                </thead>
                <tbody>
                  {substeps.map((s, i) => (
                    <tr key={i}>
                      <td>{s.process}</td>
                      {SUBSTEP_FIELDS.map(([field]) => (
                        <td key={field}>
                          <input value={s[field] || ''} onChange={(e) => setSubstepField(i, field, e.target.value)} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}

        <div className="form-row">
          <div className="form-group">
            <label>Date</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>

        {!editing && (
          <div className="form-group">
            <label>{action ? 'Cut' : 'Applies to'}</label>
            {selectable.length === 0 && <p className="muted">Nothing left to cut at this level.</p>}
            <div className="target-list">
              {selectable.map((u) => (
                <label key={u.unique_id} className="confirm-checkbox">
                  <input type="checkbox" checked={targets.includes(u.unique_id)}
                         onChange={() => toggleTarget(u.unique_id)} />
                  {u.sample_name} <span className="muted">({u.sample_type})</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {action && targets.map((parentId) => {
          const parent = units.find((u) => u.unique_id === parentId);
          const names = children[parentId] || [];
          return (
            <div key={parentId} className="children-editor">
              <label>
                {action === 'create_chiplets' ? 'Chiplets' : 'Chips'} from {parent.sample_name}:{' '}
                <input type="number" min="0" value={names.length}
                       onChange={(e) => setChildCount(parent, parseInt(e.target.value || '0', 10))} />
              </label>
              <div className="children-names">
                {names.map((n, i) => (
                  <input key={i} value={n} onChange={(e) => setChildName(parentId, i, e.target.value)} />
                ))}
              </div>
            </div>
          );
        })}

        {editing && record.created_children?.length > 0 && (
          <p className="muted">
            Created: {record.created_children.map((c) => c.sample_name).join(', ')}
          </p>
        )}

        {step.allow_files && (
          <div className="form-group">
            <label>Files (optional, e.g. recipe file)</label>
            {editing && attached === null && <p className="muted">Loading attached files...</p>}
            {editing && attached?.length > 0 && (
              <ul className="file-list">
                {attached.map((f) => (
                  <li key={f.mfid}>
                    {f.url ? <a href={f.url} target="_blank" rel="noreferrer">{f.filename}</a> : f.filename}
                  </li>
                ))}
              </ul>
            )}
            <input type="file" multiple className="file-input"
                   onChange={(e) => setNewFiles(Array.from(e.target.files))} />
          </div>
        )}

        <div className="form-group">
          <label>Comments / deviations</label>
          <textarea rows="3" value={comments} onChange={(e) => setComments(e.target.value)} />
        </div>

        {error && <div className="error-message">{error}</div>}
        {problems && (
          <div className="warning-message">
            Saved, with problems: {problems.join('; ')}
            <div><button className="btn btn-secondary btn-small" onClick={onRecorded}>OK</button></div>
          </div>
        )}

        <div className="button-group">
          {editing ? (
            <button className="btn btn-primary" onClick={() => submit(record.status)} disabled={loading}>
              {loading ? 'Saving...' : 'Save changes'}
            </button>
          ) : (
            <>
              <button className="btn btn-primary" onClick={() => submit('done')}
                      disabled={loading || !targets.length}>
                {loading ? 'Saving...' : 'Record as done'}
              </button>
              {step.optional && (
                <button className="btn btn-secondary" onClick={() => submit('skipped')}
                        disabled={loading || !targets.length}>
                  Skip step
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default StepForm;
