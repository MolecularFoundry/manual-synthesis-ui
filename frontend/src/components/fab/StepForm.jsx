import { useState } from 'react';
import { recordStep } from '../../services/api';

const ALLOWED_PARENTS = { create_chiplets: ['wafer'], create_chips: ['wafer', 'chiplet'] };
const CHILD_SUFFIX = { create_chiplets: 'CL', create_chips: 'C' };
const today = () => new Date().toISOString().split('T')[0];

const childNames = (parentName, suffix, count) =>
  Array.from({ length: count }, (_, i) => `${parentName}_${suffix}${String(i + 1).padStart(2, '0')}`);

const StepForm = ({ step, traveler, project, userInfo, earlierPending, onClose, onRecorded }) => {
  const { units, wafer, template_id: templateId } = traveler;
  const action = step.action;
  const leafUnits = units.filter((u) => u.is_leaf);
  const parentCandidates = action
    ? leafUnits.filter((u) => ALLOWED_PARENTS[action].includes(u.sample_type))
    : [];

  const [params, setParams] = useState(
    Object.fromEntries(step.parameters.map((p) => [p.key, p.default ?? '']))
  );
  const [date, setDate] = useState(today());
  const [comments, setComments] = useState('');
  const [targets, setTargets] = useState(
    action ? parentCandidates.map((u) => u.unique_id) : leafUnits.map((u) => u.unique_id)
  );
  const [children, setChildren] = useState(
    Object.fromEntries(parentCandidates.map((u) => [u.unique_id, childNames(u.sample_name, CHILD_SUFFIX[action], 4)]))
  );
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const toggleTarget = (id) =>
    setTargets((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));

  const setChildCount = (parent, count) =>
    setChildren((prev) => ({
      ...prev,
      [parent.unique_id]: childNames(parent.sample_name, CHILD_SUFFIX[action], Math.max(0, count)),
    }));

  const setChildName = (parentId, idx, name) =>
    setChildren((prev) => ({
      ...prev,
      [parentId]: prev[parentId].map((n, i) => (i === idx ? name : n)),
    }));

  const submit = async (status) => {
    setLoading(true);
    setError('');
    try {
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
        comments,
        new_children: action && status === 'done'
          ? Object.fromEntries(targets.map((t) => [t, children[t] || []]))
          : {},
      });
      if (res.success) {
        await onRecorded();
      } else {
        setResult(res);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to record step');
    } finally {
      setLoading(false);
    }
  };

  const selectable = action ? parentCandidates : units;

  return (
    <div className="modal-backdrop">
      <div className="modal-panel">
        <div className="traveler-header">
          <h3>{step.label} — {step.name}</h3>
          <button className="btn btn-secondary btn-small" onClick={onClose} disabled={loading}>Close</button>
        </div>
        {step.tool && <p className="muted">Tool: {step.tool}</p>}

        {earlierPending.length > 0 && (
          <div className="warning-message">
            Earlier required steps are still pending: {earlierPending.map((s) => s.label).join(', ')}.
            You can still record this step.
          </div>
        )}

        {step.substeps.length > 0 && (
          <details className="substeps">
            <summary>Procedure ({step.substeps.length} sub-steps)</summary>
            <ol>
              {step.substeps.map((s, i) => (
                <li key={i}>
                  <strong>{s.process}</strong>
                  {['params', 'temp', 'time', 'tool', 'specs'].filter((k) => s[k]).map((k) => (
                    <span key={k} className="muted"> · {s[k]}</span>
                  ))}
                  {s.comment && <div className="muted">{s.comment}</div>}
                </li>
              ))}
            </ol>
          </details>
        )}

        {step.parameters.length > 0 && (
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

        <div className="form-row">
          <div className="form-group">
            <label>Date</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>

        <div className="form-group">
          <label>{action ? 'Cut' : 'Applies to'}</label>
          {selectable.length === 0 && (
            <p className="muted">Nothing left to cut at this level.</p>
          )}
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

        <div className="form-group">
          <label>Comments / deviations</label>
          <textarea rows="3" value={comments} onChange={(e) => setComments(e.target.value)} />
        </div>

        {error && <div className="error-message">{error}</div>}
        {result && (
          <div className="warning-message">
            Recorded with problems: {result.errors.join('; ')}
            <div><button className="btn btn-secondary btn-small" onClick={onRecorded}>OK</button></div>
          </div>
        )}

        <div className="button-group">
          <button className="btn btn-primary" onClick={() => submit('done')} disabled={loading || !targets.length}>
            {loading ? 'Saving...' : 'Record as done'}
          </button>
          {step.optional && (
            <button className="btn btn-secondary" onClick={() => submit('skipped')} disabled={loading || !targets.length}>
              Skip step
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default StepForm;
