import { useState, useEffect, useMemo, useRef } from 'react';
import QRCode from 'qrcode';

// Mirrors the team's label_printer defaults (date, substrate, material, temp, power, rate, thickness).
const DEFAULT_CHECKED = new Set([
  'wafer_name', 'date', 'substrate_material', 'base_metal',
  'ebeam_evaporation.thickness_a', 'ebeam_evaporation.rate_a_s',
  'sputtering.thickness_nm', 'sputtering.calibrated_rate_a_s',
  'sputtering.deposition_temp_c', 'sputtering.target_output_pct',
]);

const LABEL_STYLE =
  '#label-print{width:6cm;font-size:12px;font-family:Times New Roman,serif;padding:5px;background:white;' +
  'overflow-wrap:break-word}#label-print p{margin:0}.label-qr{float:right;width:1.6cm;height:1.6cm;margin-left:4px}' +
  '.label-notes{white-space:pre-wrap}';

const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const buildFields = (traveler) => {
  const { wafer, wafer_options: options, spec, spec_record: specRecord, steps } = traveler;
  const fields = [
    { id: 'wafer_name', label: 'Wafer', value: wafer.sample_name },
    { id: 'date', label: 'Date', value: specRecord?.step_date },
    { id: 'wafer_type', label: 'Wafer type', value: options.wafer_type },
    { id: 'base_metal', label: 'Material', value: spec.base_metal },
    { id: 'substrate_material', label: 'Substrate', value: spec.substrate_material },
    { id: 'substrate_spec', label: 'Substrate spec', value: spec.substrate_spec },
    { id: 'batch_number', label: 'Batch', value: spec.batch_number },
  ];
  steps.forEach((step) => {
    const done = step.records.filter((r) => r.status === 'done');
    const last = done[done.length - 1];
    if (!last) return;
    step.parameters.forEach((p) => {
      const value = last.parameters?.[p.key];
      if (value === null || value === undefined || value === '') return;
      fields.push({
        id: `${step.id}.${p.key}`,
        label: `${step.label} ${p.label}`,
        value: p.unit ? `${value} ${p.unit}` : value,
      });
    });
  });
  return fields.filter((f) => f.value !== undefined && f.value !== null && f.value !== '');
};

const ProcessLabel = ({ traveler, onClose }) => {
  const fields = useMemo(() => buildFields(traveler), [traveler]);
  const [checked, setChecked] = useState(() => new Set(fields.filter((f) => DEFAULT_CHECKED.has(f.id)).map((f) => f.id)));
  const [notes, setNotes] = useState('');
  const [showQr, setShowQr] = useState(true);
  const [qrSrc, setQrSrc] = useState('');
  const [toast, setToast] = useState('');
  const labelRef = useRef(null);

  useEffect(() => {
    QRCode.toDataURL(traveler.wafer.explorer_url, { margin: 0, width: 160 }).then(setQrSrc);
  }, [traveler.wafer.explorer_url]);

  const toggle = (id) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const print = () => {
    // innerHTML of the React-rendered preview is already escaped.
    const win = window.open('', '_blank');
    if (!win) {
      setToast('The browser blocked the print window. Allow pop-ups for this site and try again.');
      setTimeout(() => setToast(''), 5000);
      return;
    }
    win.document.write(`<html><head><title>${escapeHtml(traveler.wafer.sample_name)}</title><style>${LABEL_STYLE}</style></head><body>`);
    win.document.write(`<div id="label-print">${labelRef.current.innerHTML}</div></body></html>`);
    win.document.close();
    // The written document has usually finished loading by now, so a load
    // handler would never fire; wait for the QR image instead, then print.
    const pending = Array.from(win.document.images)
      .filter((img) => !img.complete)
      .map((img) => new Promise((resolve) => { img.onload = resolve; img.onerror = resolve; }));
    Promise.all(pending).then(() => {
      win.focus();
      win.print();
      win.close();
    });
  };

  const capture = async () => {
    const { default: html2canvas } = await import('html2canvas');
    return html2canvas(labelRef.current, { scale: 3, backgroundColor: '#ffffff' });
  };

  const saveImage = async () => {
    const canvas = await capture();
    const link = document.createElement('a');
    link.href = canvas.toDataURL('image/png');
    link.download = `${traveler.wafer.sample_name}.png`;
    link.click();
  };

  const copyImage = async () => {
    const canvas = await capture();
    canvas.toBlob(async (blob) => {
      try {
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
        setToast(`Label for "${traveler.wafer.sample_name}" copied to clipboard.`);
      } catch {
        setToast('Failed to copy image to clipboard.');
      }
      setTimeout(() => setToast(''), 2500);
    });
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-panel">
        <div className="traveler-header">
          <h3>Create label</h3>
          <button className="btn btn-secondary btn-small" onClick={onClose}>Close</button>
        </div>

        <div className="label-layout">
          <div className="label-fields">
            {fields.map((f) => (
              <label key={f.id} className="confirm-checkbox">
                <input type="checkbox" checked={checked.has(f.id)} onChange={() => toggle(f.id)} />
                {f.label}
              </label>
            ))}
            <label className="confirm-checkbox">
              <input type="checkbox" checked={showQr} onChange={() => setShowQr(!showQr)} />
              Crucible QR code
            </label>
          </div>

          <div>
            <div id="label-print" className="label-preview" ref={labelRef}>
              {showQr && qrSrc && <img className="label-qr" src={qrSrc} alt="Crucible QR" />}
              {fields.filter((f) => checked.has(f.id)).map((f) => (
                <p key={f.id}><b>{f.label}:</b> {f.value}</p>
              ))}
              {notes.trim() && <div className="label-notes"><b>Note:</b> {notes}</div>}
            </div>
            <textarea className="label-notes-input" rows="3" placeholder="Add notes here..."
                      value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>

        <div className="button-group">
          <button className="btn btn-primary" onClick={print}>Print</button>
          <button className="btn btn-secondary" onClick={saveImage}>Save image</button>
          <button className="btn btn-secondary" onClick={copyImage}>Copy image</button>
        </div>
        {toast && <div className="success-box">{toast}</div>}
      </div>
    </div>
  );
};

export default ProcessLabel;
