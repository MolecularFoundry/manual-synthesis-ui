import logging
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor

from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File

from crucible.models import Dataset
from crucible.utils import get_tz_isoformat

from fab_templates import FAB_TEMPLATES, get_step, step_applies
from models import WaferCreateRequest, StepRecordRequest, StepEditRequest, PrintLabelRequest
from routes.synthesis import client, add_sample, get_graph_explorer_url

logger = logging.getLogger(__name__)
router = APIRouter()

PRINTER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CHILD_TYPE = {"create_chiplets": "chiplet", "create_chips": "chip"}
ALLOWED_PARENT_TYPES = {"create_chiplets": {"wafer"}, "create_chips": {"wafer", "chiplet"}}
SUBSTEP_FIELDS = ("params", "temp", "time", "tool", "specs", "comment")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # Cloud Run caps request bodies at 32 MB


def explorer_url(project, unique_id):
    return f"{get_graph_explorer_url().rstrip('/')}/{project}/samples/{unique_id}"


def get_template(template_id):
    template = FAB_TEMPLATES.get(template_id)
    if not template:
        raise HTTPException(status_code=400, detail=f"Unknown template: {template_id}")
    return template


def clean_parameters(step, values):
    """Keep only the step's declared parameters; numbers must parse."""
    cleaned = {}
    declared = {p["key"]: p for p in step["parameters"]}
    unknown = set(values) - set(declared)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown parameters for {step['label']}: {sorted(unknown)}")
    for key, param in declared.items():
        value = values.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            cleaned[key] = None
        elif param["type"] == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400,
                                    detail=f"{step['label']} '{param['label']}' must be a number, got '{value}'")
            cleaned[key] = int(number) if number.is_integer() else number
        else:
            cleaned[key] = str(value).strip()
    return cleaned


def clean_substeps(step, values):
    """Sub-step details are editable; their order and process names come from the template."""
    template_substeps = step["substeps"]
    if values is None:
        return [dict(s) for s in template_substeps]
    if len(values) != len(template_substeps):
        raise HTTPException(status_code=400, detail=f"{step['label']} expects {len(template_substeps)} sub-steps")
    cleaned = []
    for template_sub, value in zip(template_substeps, values):
        entry = {"process": template_sub["process"]}
        for field in SUBSTEP_FIELDS:
            text_value = str(value.get(field) or "").strip()
            if text_value:
                entry[field] = text_value
        cleaned.append(entry)
    return cleaned


def unit_summary(sample, parent_id, project):
    return {
        "unique_id": sample["unique_id"],
        "sample_name": sample.get("sample_name"),
        "sample_type": sample.get("sample_type"),
        "parent_id": parent_id,
        "explorer_url": explorer_url(project, sample["unique_id"]),
    }


def get_tree(wafer):
    """Wafer plus its chiplets and chips, as a flat list with parent ids."""
    project = wafer.get("project_id")
    units = [unit_summary(wafer, None, project)]
    frontier = [wafer["unique_id"]]
    while frontier:
        next_frontier = []
        for parent_id in frontier:
            for child in client.samples.list(parent_mfid=parent_id, limit=None):
                if child.get("sample_type") in ("chiplet", "chip"):
                    units.append(unit_summary(child, parent_id, project))
                    next_frontier.append(child["unique_id"])
        frontier = next_frontier
    parent_ids = {u["parent_id"] for u in units}
    for u in units:
        u["is_leaf"] = u["unique_id"] not in parent_ids
    return units


def collect_records(units, template_id):
    """Step datasets linked to any unit in the tree, keyed by dataset id."""
    def fetch(unit_id):
        return unit_id, client.datasets.list(sample_mfid=unit_id, include_metadata=True, limit=None)

    records = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for unit_id, datasets in pool.map(fetch, [u["unique_id"] for u in units]):
            for ds in datasets:
                meta = ds.get("scientific_metadata") or {}
                if meta.get("fab_template") != template_id:
                    continue
                rec = records.setdefault(ds["unique_id"], {
                    "dataset_id": ds["unique_id"],
                    "step_id": meta.get("fab_step_id"),
                    "status": meta.get("status"),
                    "step_date": meta.get("step_date"),
                    "operator": meta.get("operator"),
                    "parameters": meta.get("parameters") or {},
                    "comments": meta.get("comments"),
                    "substeps": meta.get("substeps") or [],
                    "created_children": meta.get("created_children"),
                    "edited_by": meta.get("edited_by"),
                    "edited_at": meta.get("edited_at"),
                    "wafer_options": meta.get("wafer_options"),
                    "unit_ids": [],
                })
                rec["unit_ids"].append(unit_id)
    return list(records.values())


def load_wafer(wafer_id):
    try:
        wafer = client.samples.get(wafer_id, include_datasets=False)
    except Exception:
        wafer = None
    if not wafer or wafer.get("sample_type") != "wafer":
        raise HTTPException(status_code=404, detail=f"Wafer {wafer_id} not found")
    return wafer


def find_template_id(wafer_id):
    """A traveler wafer carries its template id on its Step 0 dataset."""
    for ds in client.datasets.list(sample_mfid=wafer_id, include_metadata=True, limit=None):
        meta = ds.get("scientific_metadata") or {}
        if meta.get("fab_step_id") == "wafer_spec" and meta.get("fab_template") in FAB_TEMPLATES:
            return meta["fab_template"]
    raise HTTPException(status_code=404, detail="This wafer has no traveler (no wafer specification record)")


def create_step_dataset(project, orcid, template_id, step, wafer, metadata, target_ids):
    ds_obj = Dataset(dataset_name=f"{step['label']} {step['name']} - {wafer['sample_name']}",
                     public=False,
                     owner_orcid=orcid,
                     project_id=project,
                     measurement=step["name"],
                     timestamp=get_tz_isoformat())
    keywords = [k for k in [template_id, step["id"], step.get("tool"), wafer["sample_name"]] if k]
    new_ds = client.datasets.create(ds_obj, keywords=keywords)
    dataset_id = new_ds["created_record"]["unique_id"]
    # create() would add metadata with PATCH, which needs edit rights the service account lacks
    client._request("post", f"/resources/{dataset_id}/metadata", json=metadata)

    link_errors = []
    for target_id in target_ids:
        try:
            client.samples.link_dataset(target_id, dataset_id)
        except Exception as err:
            logger.error(f"Linking dataset {dataset_id} to {target_id} failed: {err}")
            link_errors.append(f"{target_id}: {err}")
    return dataset_id, link_errors


def step_metadata(template_id, step, wafer, req_status, step_date, operator, parameters, substeps, comments,
                  **extra):
    return {
        "fab_template": template_id,
        "fab_step_id": step["id"],
        "step_label": step["label"],
        "step_name": step["name"],
        "status": req_status,
        "step_date": step_date,
        "operator": operator,
        "wafer_id": wafer["unique_id"],
        "wafer_name": wafer["sample_name"],
        "parameters": parameters,
        "substeps": substeps,
        "comments": comments,
        **extra,
    }


def name_taken(name, project):
    return bool(client.samples.list(sample_name=name, project_id=project))


@router.get("/templates")
async def list_templates():
    return {"templates": FAB_TEMPLATES}


@router.get("/wafers")
async def list_wafers(project: str):
    wafers = client.samples.list(project_id=project, sample_type="wafer", limit=None)
    return {"wafers": [{
        "unique_id": w["unique_id"],
        "sample_name": w.get("sample_name"),
        "description": w.get("description"),
        "timestamp": w.get("timestamp"),
    } for w in wafers]}


@router.post("/wafers")
async def create_wafer(req: WaferCreateRequest):
    template = get_template(req.template_id)
    name = req.wafer_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Wafer name is required")
    for option, allowed in template["wafer_options"].items():
        if req.wafer_options.get(option) not in allowed:
            raise HTTPException(status_code=400, detail=f"'{option}' must be one of {allowed}")
    if name_taken(name, req.project):
        raise HTTPException(status_code=409, detail=f"A sample named '{name}' already exists in {req.project}")

    spec_step = template["wafer_spec"]
    spec = clean_parameters(spec_step, req.spec)
    wafer_options = {k: req.wafer_options[k] for k in template["wafer_options"]}

    new_wafer = add_sample(orcid=req.orcid, project=req.project, sample_name=name,
                           description=req.description, sample_type="wafer")
    wafer = {"unique_id": new_wafer["unique_id"], "sample_name": name}
    step_date = req.step_date or get_tz_isoformat()[:10]
    metadata = step_metadata(req.template_id, spec_step, wafer, "done", step_date, req.operator,
                             spec, [], None, wafer_options=wafer_options)
    dataset_id, link_errors = create_step_dataset(req.project, req.orcid, req.template_id, spec_step,
                                                  wafer, metadata, [wafer["unique_id"]])
    return {"wafer": {**wafer, "explorer_url": explorer_url(req.project, wafer["unique_id"])},
            "dataset_id": dataset_id, "errors": link_errors}


@router.get("/wafers/{wafer_id}/traveler")
async def get_traveler(wafer_id: str):
    wafer = load_wafer(wafer_id)
    template_id = find_template_id(wafer_id)
    template = FAB_TEMPLATES[template_id]
    units = get_tree(wafer)
    records = collect_records(units, template_id)

    spec_record = next((r for r in records if r["step_id"] == "wafer_spec"), None)
    wafer_options = (spec_record or {}).get("wafer_options") or {}

    steps = []
    for step in template["steps"]:
        if not step_applies(step, wafer_options):
            continue
        step_records = sorted((r for r in records if r["step_id"] == step["id"]),
                              key=lambda r: r["step_date"] or "")
        statuses = {r["status"] for r in step_records}
        status = "done" if "done" in statuses else "skipped" if statuses else "pending"
        steps.append({**step, "status": status, "records": step_records})

    return {
        "template_id": template_id,
        "template_name": template["name"],
        "label_after_step": template.get("label_after_step"),
        "wafer": units[0],
        "wafer_options": wafer_options,
        "spec": (spec_record or {}).get("parameters") or {},
        "spec_record": spec_record,
        "units": units,
        "steps": steps,
    }


@router.post("/steps")
async def record_step(req: StepRecordRequest):
    get_template(req.template_id)
    step = get_step(req.template_id, req.step_id)
    if not step or step["id"] == "wafer_spec":
        raise HTTPException(status_code=400, detail=f"Unknown step: {req.step_id}")
    if req.status == "skipped" and not step["optional"]:
        raise HTTPException(status_code=400, detail=f"{step['label']} is required and can't be skipped")

    wafer = load_wafer(req.wafer_id)
    if find_template_id(req.wafer_id) != req.template_id:
        raise HTTPException(status_code=400, detail="Template does not match this wafer's traveler")
    units = get_tree(wafer)
    unit_by_id = {u["unique_id"]: u for u in units}

    spec_record = next((r for r in collect_records(units[:1], req.template_id)
                        if r["step_id"] == "wafer_spec"), None)
    if not step_applies(step, (spec_record or {}).get("wafer_options") or {}):
        raise HTTPException(status_code=400, detail=f"{step['label']} does not apply to this wafer")

    target_ids = list(dict.fromkeys(req.target_ids))
    if not target_ids:
        raise HTTPException(status_code=400, detail="Select at least one wafer/chiplet/chip")
    outside = [t for t in target_ids if t not in unit_by_id]
    if outside:
        raise HTTPException(status_code=400, detail=f"Not part of this wafer: {outside}")

    parameters = clean_parameters(step, req.parameters) if req.status == "done" else {}
    substeps = clean_substeps(step, req.substeps)

    created = []
    errors = []
    action = step.get("action")
    if action and req.status == "done":
        child_type = CHILD_TYPE[action]
        planned = []
        for parent_id, names in req.new_children.items():
            parent = unit_by_id.get(parent_id)
            if not parent or parent["sample_type"] not in ALLOWED_PARENT_TYPES[action]:
                raise HTTPException(status_code=400, detail=f"Can't create {child_type}s under {parent_id}")
            if not parent["is_leaf"]:
                raise HTTPException(status_code=400,
                                    detail=f"{parent['sample_name']} has already been cut")
            for name in names:
                if name.strip():
                    planned.append((parent_id, name.strip()))
        if not planned:
            raise HTTPException(status_code=400, detail=f"Enter at least one {child_type} name")
        all_names = [n for _, n in planned]
        dupes = sorted({n for n in all_names if all_names.count(n) > 1})
        if dupes:
            raise HTTPException(status_code=400, detail=f"Duplicate names: {dupes}")
        taken = [n for n in all_names if name_taken(n, req.project)]
        if taken:
            raise HTTPException(status_code=409, detail=f"Names already used in {req.project}: {taken}")

        for parent_id, name in planned:
            try:
                child = add_sample(orcid=req.orcid, project=req.project, sample_name=name,
                                   description=f"{child_type} of {unit_by_id[parent_id]['sample_name']}",
                                   sample_type=child_type)
                client.samples.link(parent_id, child["unique_id"])
                created.append({"unique_id": child["unique_id"], "sample_name": name,
                                "sample_type": child_type, "parent_id": parent_id,
                                "explorer_url": explorer_url(req.project, child["unique_id"])})
            except Exception as err:
                logger.error(f"Creating {child_type} {name} failed: {err}")
                errors.append(f"{name}: {err}")
        # The cut is recorded on the units that were cut.
        target_ids = list(dict.fromkeys(p for p, _ in planned))

    metadata = step_metadata(req.template_id, step, wafer, req.status, req.step_date, req.operator,
                             parameters, substeps, req.comments, created_children=created or None)
    dataset_id, link_errors = create_step_dataset(req.project, req.orcid, req.template_id, step,
                                                  wafer, metadata, target_ids)
    errors.extend(link_errors)
    return {"success": not errors, "dataset_id": dataset_id, "created": created, "errors": errors}


@router.get("/printers")
async def list_printers():
    # Not wrapped by nano-crucible yet.
    return {"printers": client._request("get", "/print/printers").get("printers", [])}


@router.post("/print")
async def print_label(req: PrintLabelRequest):
    printer_id = req.printer_id.strip()
    if not PRINTER_ID_RE.fullmatch(printer_id):
        raise HTTPException(status_code=400, detail=f"'{printer_id}' is not a valid printer id")
    try:
        sample = client.samples.get(req.sample_id, include_datasets=False)
    except Exception:
        sample = None
    if not sample:
        raise HTTPException(status_code=404, detail=f"Sample {req.sample_id} not found")
    result = client.print.barcode(printer_id=printer_id, mfid=sample["unique_id"],
                                  name=sample.get("sample_name") or "")
    status = result.get("status")
    return {"success": status == "ok", "status": status,
            "detail": result.get("detail") or (None if status == "ok" else f"Printer reported status={status}")}


def http_status(err):
    response = getattr(err, "response", None)
    return getattr(response, "status_code", None)


def load_step_record(dataset_id):
    try:
        ds = client.datasets.get(dataset_id, include_metadata=True)
    except Exception:
        ds = None
    meta = (ds or {}).get("scientific_metadata") or {}
    template_id = meta.get("fab_template")
    step = get_step(template_id, meta.get("fab_step_id")) if template_id in FAB_TEMPLATES else None
    if not step:
        raise HTTPException(status_code=404, detail=f"No traveler step record {dataset_id}")
    return meta, step


@router.get("/steps/{dataset_id}")
async def get_step_record(dataset_id: str):
    meta, step = load_step_record(dataset_id)
    files = client.datasets.list_files(dataset_id)
    try:
        links = client.datasets.get_download_links(dataset_id) if files else {}
    except Exception as err:
        logger.warning(f"Download links for {dataset_id} unavailable: {err}")
        links = {}
    return {
        "dataset_id": dataset_id,
        "step": step,
        "record": meta,
        "files": [{"mfid": f.get("mfid"), "filename": f.get("filename"), "size": f.get("size"),
                   "url": links.get(f.get("mfid"))} for f in files],
    }


@router.put("/steps/{dataset_id}")
async def edit_step_record(dataset_id: str, req: StepEditRequest):
    meta, step = load_step_record(dataset_id)
    updated = {
        **meta,
        "step_date": req.step_date,
        "parameters": clean_parameters(step, req.parameters) if meta.get("status") == "done" else {},
        "substeps": clean_substeps(step, req.substeps),
        "comments": req.comments,
        "edited_by": req.operator,
        "edited_at": get_tz_isoformat(),
    }
    try:
        client.datasets.update_scientific_metadata(dataset_id, updated, overwrite=True)
    except Exception as err:
        if http_status(err) == 403:
            raise HTTPException(status_code=403,
                                detail="Editing needs edit permission for the app's service account "
                                       "on this Crucible project. Ask a Crucible admin to grant it.")
        raise
    return {"success": True, "record": updated}


@router.post("/steps/{dataset_id}/files")
async def upload_step_files(dataset_id: str, files: List[UploadFile] = File(...)):
    _, step = load_step_record(dataset_id)
    if not step.get("allow_files"):
        raise HTTPException(status_code=400, detail=f"{step['label']} does not take file attachments")

    uploaded, errors = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for upload in files:
            filename = os.path.basename(upload.filename or "").strip()
            if not filename or filename in (".", ".."):
                errors.append("A file without a name was skipped")
                continue
            content = await upload.read()
            if len(content) > MAX_UPLOAD_BYTES:
                errors.append(f"{filename}: larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
                continue
            path = os.path.join(tmp, filename)
            with open(path, "wb") as fh:
                fh.write(content)
            try:
                client.datasets.add_file(dataset_id, path, skip_ingestion=True)
                uploaded.append(filename)
            except Exception as err:
                logger.error(f"Uploading {filename} to {dataset_id} failed: {err}")
                errors.append(f"{filename}: {err}")
    return {"success": not errors, "uploaded": uploaded, "errors": errors}
