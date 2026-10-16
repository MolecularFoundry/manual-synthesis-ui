import os
from dotenv import load_dotenv
import logging
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from models import (SynthesisFieldsResponse, SynthesisUploadRequest, SynthesisUploadResponse,
                    AmbiguousParent, UnresolvedParent, ParentCandidate, DuplicateName)

from crucible import CrucibleClient
from crucible.config import get_graph_explorer_url
from crucible.models import Dataset, Sample
from crucible.utils import get_tz_isoformat

# Chem Utils
from rdkit import Chem
from rdkit import RDLogger


def canonical(smi):
    """Return canonical SMILES, or None if parsing fails or input is empty."""
    if not isinstance(smi, str) or not smi.strip():
        return None
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


logger = logging.getLogger(__name__)
router = APIRouter()

RUN_ENV = os.getenv('RUN_ENV')
if RUN_ENV != 'cloud':
    load_dotenv()

crucible_url = "https://crucible.lbl.gov/api/v3"
admin_apikey = os.environ.get('ADMIN_APIKEY')
client = CrucibleClient(crucible_url, admin_apikey)
logger.info(f"Crucible client initialized with URL: {crucible_url}")

# =============================================================================
# SYNTHESIS DATASET FIELD DEFINITIONS
#
# Categories group synthesis types that belong to the same project/workflow.
# Type names (e.g. "Stock Solution") may repeat across categories with
# entirely different columns and parent rules, so all lookups are scoped by
# category first.
# =============================================================================

SYNTHESIS_CATEGORIES = {
    "Perovskites_10k": {
        "fields": {
            "Solid Precursor": [
                "Sample Name", "Sample Description", "Notes", "CAS", "RFID", "Name", "SMILES", "Abbrev",
                "Vendor", "Opened Timestamp", "Storage Location", 'NMR_ID'
            ],
            "Stock Solution": [
                "Sample Name", "Sample Description", "Notes", "Organic Salt SP-ID", "Organic Salt Name",
                "Organic Cation Actual Weight mg", "Metal Salt SP-ID", "Metal Salt Name",
                "Metal Cation Actual Weight mg", "Solvent", "Solvent Volume ml",
                "Target Concentration mol", "Storage Location"
            ],
            "Precursor Solution": [
                "Sample Name", "Sample Description", "Notes", "Target Stoichiometry", "Component A SS-ID",
                "Component B SS-ID", "SMILES_Organic", "SMILES_Metal", "Mixing Ratio", "Target Concentration (M)",
                "Storage Location", "PS Autobot Recipe Filename"
            ],
        },
        # Which columns hold parent references, and what sample_type each one
        # must resolve against. A stock solution is always made from solid
        # precursors; a precursor solution always from stock solutions.
        # Filtering the lookup by type removes most name collisions before
        # they can reach the user.
        "parents": {
            "Stock Solution": {
                "organic_salt_sp-id": {"label": "Organic Salt SP-ID", "parent_type": "solid precursor"},
                "metal_salt_sp-id": {"label": "Metal Salt SP-ID", "parent_type": "solid precursor"},
            },
            "Precursor Solution": {
                "component_a_ss-id": {"label": "Component A SS-ID", "parent_type": "stock solution"},
                "component_b_ss-id": {"label": "Component B SS-ID", "parent_type": "stock solution"},
            },
        },
    },
    "Solgel_Opentrons_Paige": {
        "fields": {
            "Solid Precursor": [
                "Sample Name", "Sample Description", "Notes", "CAS", "RFID", "Name", "SMILES", "Abbrev.",
                "Vendor", "Opened Timestamp", "Storage Location", "NMR_ID"
            ],
            "Stock Solution": [
                "Sample Name", "Sample Description", "Notes", "Metal Salt SP-ID", "Metal Salt Name",
                "Metal Cation Actual Weight mg", "Citric Acid SP-ID", "Citric Acid Actual Weight mg",
                "Solvent", "Solvent Volume ml", "Target Concentration (M)", "Storage Location"
            ],
            "Precursor Solution": [
                "Sample Name", "Sample Description", "Notes", "Target Stoichiometry", "Preparation Method",
                "Target Total Volume (uL)", "Mn Precursor SS-ID", "Mn Precursor Volume uL",
                "Ca Precursor SS-ID", "Ca Precursor Volume uL", "Sr Precursor SS-ID", "Sr Precursor Volume uL",
                "Y Precursor SS-ID", "Y Precursor Volume uL", "Fe Precursor SS-ID", "Fe Precursor Volume uL",
                "Ti Precursor SS-ID", "Ti Precursor Volume uL", "Citric Acid SP-ID",
                "Citric Acid Precursor weight mg", "Ethylene Glycol SP-ID", "EG Volume uL",
                "Storage Location", "Opentrons Recipe Filename"
            ],
        },
        "parents": {
            "Stock Solution": {
                "metal_salt_sp-id": {"label": "Metal Salt SP-ID", "parent_type": "solid precursor"},
                "citric_acid_sp-id": {"label": "Citric Acid SP-ID", "parent_type": "solid precursor"},
            },
            "Precursor Solution": {
                "mn_precursor_ss-id": {"label": "Mn Precursor SS-ID", "parent_type": "stock solution"},
                "ca_precursor_ss-id": {"label": "Ca Precursor SS-ID", "parent_type": "stock solution"},
                "sr_precursor_ss-id": {"label": "Sr Precursor SS-ID", "parent_type": "stock solution"},
                "y_precursor_ss-id": {"label": "Y Precursor SS-ID", "parent_type": "stock solution"},
                "fe_precursor_ss-id": {"label": "Fe Precursor SS-ID", "parent_type": "stock solution"},
                "ti_precursor_ss-id": {"label": "Ti Precursor SS-ID", "parent_type": "stock solution"},
                # These two reference the original solid precursor containers
                # directly, not a stock solution made from them.
                "citric_acid_sp-id": {"label": "Citric Acid SP-ID", "parent_type": "solid precursor"},
                "ethylene_glycol_sp-id": {"label": "Ethylene Glycol SP-ID", "parent_type": "solid precursor"},
            },
        },
    },
}

CRUCIBLE_ID_LENGTH = 26


def add_sample(orcid, project, sample_name, description, sample_type=None):
    logger.debug(f"Adding sample to database: name={sample_name}, project={project}, orcid={orcid}")
    today_date = get_tz_isoformat()
    new_samp = client.samples.create(Sample(sample_name=sample_name, sample_type=sample_type,
                                            description=description, timestamp=today_date,
                                            owner_orcid=orcid, project_id=project))
    logger.debug(f"Sample added to Crucible: {new_samp}")
    return {
        'sample_name': sample_name,
        'description': description,
        'project': project,
        'unique_id': new_samp['unique_id'],
        'timestamp': today_date
    }


def add_synthesis_dataset(orcid, project, ds_record, synthesis_type, user_name, sample_uuid, session_name=None):
    sample_name = ds_record['sample_name']
    dataset_name = f'{synthesis_type} recipe for {sample_name}'
    ds_obj = Dataset(dataset_name=dataset_name,
                     public=False,
                     owner_orcid=orcid,
                     project_id=project,
                     measurement=f"{synthesis_type} synthesis",
                     session_name=session_name,
                     timestamp=ds_record['timestamp'])
    keywords = [k for k in [synthesis_type, sample_name, session_name] if k is not None]
    new_ds = client.datasets.create(ds_obj, keywords=keywords)
    dataset_mfid = new_ds['created_record']['unique_id']
    # create() adds metadata with PATCH, which needs edit rights the service account lacks on datasets it creates for users
    client._request('post', f'/resources/{dataset_mfid}/metadata', json=ds_record)
    client.samples.add_dataset(sample_id=sample_uuid, dataset_id=dataset_mfid)


def _candidate(sample):
    return ParentCandidate(
        unique_id=sample['unique_id'],
        sample_name=sample['sample_name'],
        sample_type=sample.get('sample_type'),
        date_created=sample.get('timestamp') or sample.get('creation_time'),
        description=sample.get('description'),
    )


def _selection_is_valid(unique_id, project, parent_type):
    """The client echoes selections back to us, so re-check them before linking."""
    try:
        sample = client.samples.get(unique_id)
    except Exception:
        return False
    return bool(sample) and sample.get('project_id') == project \
        and sample.get('sample_type') == parent_type


def resolve_parent_reference(reference, project, parent_type):
    """
    Resolve one parent reference to a sample unique_id.

    Returns (unique_id, candidates). A unique_id means the reference resolved.
    Otherwise candidates holds the competing matches, which is empty when
    nothing matched at all.
    """
    reference = str(reference).strip()

    # The sheet's *-ID columns may hold a real Crucible id rather than a name.
    if len(reference) == CRUCIBLE_ID_LENGTH:
        try:
            found = client.samples.get(reference)
        except Exception:
            found = None
        if found:
            return found['unique_id'], []

    matches = client.samples.list(sample_name=reference,
                                  project_id=project,
                                  sample_type=parent_type)
    if len(matches) == 1:
        return matches[0]['unique_id'], []
    return None, matches


def validate_rows(records, project, category, synthesis_type, selections):
    """
    Read-only pass. Resolves every parent reference and looks for sample names
    already present in the project. Writes nothing.

    Returns (resolved, ambiguous, unresolved, duplicates) where resolved maps
    (row, field) to a parent unique_id.
    """
    parent_conf = SYNTHESIS_CATEGORIES[category]["parents"].get(synthesis_type)
    resolved = {}
    ambiguous = []
    unresolved = []
    duplicates = []

    for row, record in records:
        sample_name = record.get('sample_name')

        if sample_name:
            existing = client.samples.list(sample_name=sample_name, project_id=project)
            if existing:
                duplicates.append(DuplicateName(
                    row=row,
                    sample_name=sample_name,
                    existing_count=len(existing),
                    existing_ids=[e['unique_id'] for e in existing],
                ))

        if not parent_conf:
            continue

        for field, field_conf in parent_conf.items():
            field_label = field_conf['label']
            parent_type = field_conf['parent_type']
            reference = record.get(field)
            if reference is None or not str(reference).strip():
                continue

            chosen = selections.get((row, field))
            if chosen and _selection_is_valid(chosen, project, parent_type):
                resolved[(row, field)] = chosen
                continue

            parent_id, candidates = resolve_parent_reference(
                reference, project, parent_type)

            if parent_id:
                resolved[(row, field)] = parent_id
            elif candidates:
                ambiguous.append(AmbiguousParent(
                    row=row,
                    sample_name=sample_name,
                    field=field,
                    field_label=field_label,
                    reference=str(reference).strip(),
                    candidates=[_candidate(c) for c in candidates],
                ))
            else:
                unresolved.append(UnresolvedParent(
                    row=row,
                    sample_name=sample_name,
                    field=field,
                    field_label=field_label,
                    reference=str(reference).strip(),
                    expected_type=parent_type,
                ))

    return resolved, ambiguous, unresolved, duplicates


def prepare_records(dataset_df):
    """Normalise the sheet and pair each row with its original position."""
    dataset_df = dataset_df.replace('', np.nan).dropna(how='all')
    dataset_df = dataset_df.replace(np.nan, None)
    dataset_df.columns = [x.lower().replace(' ', '_') for x in dataset_df.columns]
    # dropna keeps the original labels, so the index still points at the row
    # the user sees in their spreadsheet.
    return list(zip(dataset_df.index.tolist(), dataset_df.to_dict('records')))


def upload_all_sample_synthesis_info(orcid, project, records, category, synthesis_type, user_name,
                                     resolved, unresolved, session_name=None):
    logger.debug(f"Adding {len(records)} rows of {synthesis_type} dataset to project {project}")

    parent_conf = SYNTHESIS_CATEGORIES[category]["parents"].get(synthesis_type, {})
    parent_field_names = list(parent_conf)

    # Rows whose parent reference matched nothing are skipped outright rather
    # than written without their genealogy.
    skip = {}
    for u in unresolved:
        skip.setdefault(u.row, []).append(
            f"{u.field_label} '{u.reference}' matched no {u.expected_type}")

    success_count = 0
    failed_count = 0
    error_messages = []
    created_samples = []

    for row, record in records:
        display_row = row + 1
        sample_name = record.get('sample_name', 'Unknown')

        if row in skip:
            failed_count += 1
            error_messages.append(
                f"Row {display_row} '{sample_name}': {'; '.join(skip[row])} — row skipped, nothing written")
            continue

        try:
            new_samp = add_sample(orcid=orcid, project=project,
                                  sample_name=record['sample_name'],
                                  description=record['sample_description'],
                                  sample_type=synthesis_type.lower())
            sample_uuid = new_samp['unique_id']
            created_samples.append({
                'sample_name': record['sample_name'],
                'unique_id': sample_uuid,
                'explorer_url': f"{get_graph_explorer_url().rstrip('/')}/{project}/samples/{sample_uuid}",
            })

            for field in parent_field_names:
                parent_id = resolved.get((row, field))
                if parent_id:
                    client.samples.link(parent_id, sample_uuid)

            canonical_updates = {f'{k}_canonical': canonical(v) for k,v in record.items() if 'smiles' in k.lower()}
            record.update(canonical_updates)

            add_synthesis_dataset(orcid, project, record, synthesis_type, user_name,
                                  sample_uuid, session_name)
            success_count += 1

        except Exception as err:
            failed_count += 1
            error_messages.append(f"Row {display_row} '{sample_name}': {str(err)}")
            logger.error(f"dataset upload failed for {record} with error: {err}")

    summary = {
        "Project": project,
        "Synthesis Type": synthesis_type,
        "Samples Uploaded": success_count,
        "Failed": failed_count,
        "Total Rows": len(records),
        "Created Samples": created_samples
    }
    if error_messages:
        summary["Errors"] = error_messages

    if failed_count == 0 and success_count > 0:
        status_msg = f"Successfully uploaded {success_count} samples to project '{project}'"
    elif success_count == 0 and failed_count > 0:
        status_msg = f"Upload failed: All {failed_count} samples failed to upload"
    elif success_count > 0 and failed_count > 0:
        status_msg = f"Partial upload: {success_count} samples uploaded successfully, {failed_count} failed"
    else:
        status_msg = "No samples to upload"

    return status_msg, summary


@router.get("/fields", response_model=SynthesisFieldsResponse)
async def get_synthesis_fields():
    try:
        logger.info("Fetching synthesis fields")
        categories = {name: conf["fields"] for name, conf in SYNTHESIS_CATEGORIES.items()}
        return SynthesisFieldsResponse(categories=categories)
    except Exception as e:
        logger.error(f"Error fetching synthesis fields: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=SynthesisUploadResponse)
async def upload_synthesis_data(request: SynthesisUploadRequest):
    try:
        logger.info(f"Upload request: {request.category} / {request.synthesis_type} for project {request.project}")
        logger.info(f"Data rows: {len(request.data)}")

        if request.category not in SYNTHESIS_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Unknown synthesis category: {request.category}")

        if not request.data or len(request.data) == 0:
            return SynthesisUploadResponse(success=False, message="No data provided for upload")

        records = prepare_records(pd.DataFrame(request.data))
        selections = {(s.row, s.field): s.unique_id for s in request.parent_selections}

        # Pass 1 is read-only, so halting here leaves Crucible untouched.
        resolved, ambiguous, unresolved, duplicates = validate_rows(
            records, request.project, request.category, request.synthesis_type, selections)

        if ambiguous:
            logger.info(f"Upload halted: {len(ambiguous)} parent reference(s) need selection")
            return SynthesisUploadResponse(
                success=False,
                message=f"{len(ambiguous)} parent reference(s) match more than one sample. "
                        f"Choose which one to link, then upload again. Nothing has been uploaded yet.",
                needs_selection=ambiguous,
                unresolved_parents=unresolved,
                duplicate_names=duplicates,
            )

        if duplicates and not request.confirm_duplicate_names:
            logger.info(f"Upload halted: {len(duplicates)} row(s) reuse an existing sample name")
            return SynthesisUploadResponse(
                success=False,
                message=f"{len(duplicates)} of {len(records)} rows use a Sample Name that already "
                        f"exists in '{request.project}'. Confirm to upload them anyway. "
                        f"Nothing has been uploaded yet.",
                unresolved_parents=unresolved,
                duplicate_names=duplicates,
            )

        status_msg, summary = upload_all_sample_synthesis_info(
            orcid=request.orcid,
            project=request.project,
            records=records,
            category=request.category,
            synthesis_type=request.synthesis_type,
            user_name=request.user_name,
            resolved=resolved,
            unresolved=unresolved,
            session_name=request.session_name
        )

        logger.info(f"Upload completed: {status_msg}")
        return SynthesisUploadResponse(success=True, message=status_msg, summary=summary)

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
