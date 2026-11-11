"""End-to-end checks of the /api/fab routes against an in-memory Crucible.

Run from backend/:  python tests/test_fabrication.py
"""
import os
import sys

os.environ.setdefault("RUN_ENV", "cloud")
os.environ.setdefault("ADMIN_APIKEY", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

import fake_crucible  # noqa: E402
import main  # noqa: E402
from routes import synthesis  # noqa: E402

store = fake_crucible.install(synthesis.client)
api = TestClient(main.app)
P, T = "QCMF_TEST", "QCMF_Qubit_v1"
base = {"project": P, "orcid": "0000-0001", "operator": "Tim"}
results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


def fields(step_def, row_key):
    return {f["key"]: f for f in next(r for r in step_def["rows"] if r["key"] == row_key)["fields"]}


def step(wafer_id, step_id, targets, status="done", rows=None, new_children=None):
    body = {**base, "template_id": T, "step_id": step_id, "wafer_id": wafer_id, "target_ids": targets,
            "status": status, "step_date": "2026-11-10", "rows": rows or {}, "comments": "c",
            "new_children": new_children or {}}
    return api.post("/api/fab/steps", json=body)


check("templates listed", T in api.get("/api/fab/templates").json()["templates"])

r = api.post("/api/fab/wafers", json={**base, "template_id": T, "wafer_name": "QCMF_WFR_99",
                                      "wafer_options": {"wafer_type": "qubit"},
                                      "spec": {"batch_number": "B7", "base_metal": "Al"}})
check("wafer created", r.status_code == 200)
wid = r.json()["wafer"]["unique_id"]
check("duplicate wafer name -> 409", api.post("/api/fab/wafers", json={
    **base, "template_id": T, "wafer_name": "QCMF_WFR_99", "wafer_options": {"wafer_type": "qubit"}}).status_code == 409)
check("invalid wafer type -> 400", api.post("/api/fab/wafers", json={
    **base, "template_id": T, "wafer_name": "X", "wafer_options": {"wafer_type": "prod"}}).status_code == 400)

trav = api.get(f"/api/fab/wafers/{wid}/traveler").json()
labels = {s["label"]: s for s in trav["steps"]}
check("qubit variants only", "Step 1A" in labels and "Step 1B" not in labels and "Step 10B" not in labels)
check("3A/3B/8A/8B/9 all available and optional",
      all(labels[l]["optional"] for l in ["Step 3A", "Step 3B", "Step 8A", "Step 8B", "Step 9"]))
check("renamed deposition steps", labels["Step 3A"]["name"] == "E-beam evaporation"
      and labels["Step 3B"]["name"] == "Sputtering")
check("chiplets are Step 14, post clean Step 21", labels["Step 14"]["id"] == "cut_chiplets"
      and labels["Step 21"]["id"] == "jj_post_clean" and "Step 13b" not in labels)
check("file uploads on the requested steps",
      sorted(l for l, s in labels.items() if s.get("allow_files"))
      == sorted(["Step 2", "Step 5", "Step 7", "Step 8A", "Step 8B", "Step 11", "Step 15", "Step 17"]))
check("split times", {"strike_time_s", "etch_time_s"} <= set(fields(labels["Step 7"], "o2_descum"))
      and {"strike_time_s", "etch_time_s"} <= set(fields(labels["Step 15"], "o2_descum"))
      and {"etch1_time_s", "etch2_time_s"} <= set(fields(labels["Step 9"], "trench_etch")))
check("liftoff NMP time in minutes", fields(labels["Step 20"], "nmp_1_hotplate")["time_min"]["default"] == 120)
check("rows carry their own units", fields(labels["Step 1A"], "diw_rinse")["time_s"]["unit"] == "s"
      and fields(labels["Step 1A"], "rca_1_clean")["time_min"]["unit"] == "min")
check("RT became 20 C", fields(labels["Step 2"], "boe_dip")["temp_c"]["default"] == 20)
check("base metal stored as spec", trav["spec"]["base_metal"] == "Al")

r = step(wid, "rca_clean", [wid], rows={"rca_1_clean": {"temp_c": "90", "time_min": 20, "tool": "Hotplate"},
                                       "diw_rinse": {"temp_c": 20, "time_s": "20"}})
check("record step 1A", r.status_code == 200 and r.json()["success"])
ds_id = r.json()["dataset_id"]
meta = store["datasets"][ds_id]["scientific_metadata"]
check("rows stored in template order", [r["key"] for r in meta["rows"]]
      == ["rca_1_clean", "diw_beaker_1", "diw_beaker_2", "diw_rinse", "n2_blow_dry"])
check("flat searchable values, numbers parsed", meta["values"] == {
      "rca_1_clean_temp_c": 90, "rca_1_clean_time_min": 20, "rca_1_clean_tool": "Hotplate",
      "diw_rinse_temp_c": 20, "diw_rinse_time_s": 20} and meta["fab_step_id"] == "rca_clean")

r = step(wid, "native_oxide_removal", [wid], rows={"boe_dip": {"time_min": "1.5", "chemistry": "7:1 mixture"}})
m2 = store["datasets"][r.json()["dataset_id"]]["scientific_metadata"]
check("text + decimal values saved", m2["values"]["boe_dip_time_min"] == 1.5 and m2["values"]["boe_dip_chemistry"] == "7:1 mixture")
check("unknown row -> 400", step(wid, "native_oxide_removal", [wid], rows={"nope": {"temp_c": 1}}).status_code == 400)
check("unknown field -> 400", step(wid, "native_oxide_removal", [wid], rows={"boe_dip": {"rpm": 1}}).status_code == 400)
step2_id = r.json()["dataset_id"]

check("both 3A and 3B can be recorded", step(wid, "ebeam_evaporation", [wid]).status_code == 200
      and step(wid, "sputtering", [wid]).status_code == 200)
check("bad number -> 400", step(wid, "exposure", [wid], rows={"expose": {"dose_mj_cm2": "lots"}}).status_code == 400)
check("bad number in another row -> 400", step(wid, "exposure", [wid], rows={"expose": {"defocus": "x"}}).status_code == 400)
check("skip required -> 400", step(wid, "exposure", [wid], status="skipped").status_code == 400)
check("skip optional ok", step(wid, "wafer_trench", [wid], status="skipped").status_code == 200)
check("foreign target -> 400", step(wid, "exposure", ["S_nope"]).status_code == 400)

# View + edit in place
rec = api.get(f"/api/fab/steps/{ds_id}").json()
check("view record", rec["record"]["values"]["rca_1_clean_time_min"] == 20 and rec["files"] == [])
edit = {**base, "step_date": "2026-11-09", "rows": {"rca_1_clean": {"temp_c": 85, "time_min": 25}},
        "comments": "fixed typo"}
r = api.put(f"/api/fab/steps/{ds_id}", json=edit)
m3 = store["datasets"][ds_id]["scientific_metadata"]
check("edit overwrites in place", r.status_code == 200 and m3["values"]["rca_1_clean_time_min"] == 25
      and m3["step_date"] == "2026-11-09" and m3["edited_by"] == "Tim" and m3["operator"] == "Tim"
      and m3["fab_step_id"] == "rca_clean")
store["can_edit"] = False
r = api.put(f"/api/fab/steps/{ds_id}", json=edit)
check("edit without permission -> clear 403", r.status_code == 403 and "edit permission" in r.json()["detail"])
store["can_edit"] = True
check("edit unknown record -> 404", api.put("/api/fab/steps/D_nope", json=edit).status_code == 404)

# Files
r = api.post(f"/api/fab/steps/{step2_id}/files", files=[("files", ("boe_recipe.txt", b"BOE 10:1, 60 s", "text/plain"))])
check("file uploaded without ingestion", r.status_code == 200 and r.json()["uploaded"] == ["boe_recipe.txt"]
      and store["files"][step2_id][0]["skip_ingestion"] is True)
r = api.post(f"/api/fab/steps/{step2_id}/files", files=[("files", ("boe_recipe.txt", b"other", "text/plain"))])
check("duplicate filename reported", r.status_code == 200 and not r.json()["success"])
check("files listed with links", api.get(f"/api/fab/steps/{step2_id}").json()["files"][0]["url"].endswith("boe_recipe.txt"))
r = api.post(f"/api/fab/steps/{ds_id}/files", files=[("files", ("x.txt", b"x", "text/plain"))])
check("files refused on steps without uploads", r.status_code == 400)

# Chiplets, dicing, multi-target steps
r = step(wid, "cut_chiplets", [wid], new_children={wid: ["WFR99_CL01", "WFR99_CL02"]})
check("chiplets created", r.status_code == 200 and len(r.json()["created"]) == 2)
cl = [c["unique_id"] for c in r.json()["created"]]
check("re-cut wafer -> 400", step(wid, "cut_chiplets", [wid], new_children={wid: ["CLX"]}).status_code == 400)
check("dup child names -> 400", step(wid, "dicing", cl, new_children={cl[0]: ["A", "A"]}).status_code == 400)
r = step(wid, "jj_deposition", cl, rows={"oxidation": {"time_s": 600, "pressure_torr": 12}})
check("step on both chiplets", r.status_code == 200
      and {(c, r.json()["dataset_id"]) for c in cl} <= set(store["sample_datasets"]))
r = step(wid, "dicing", cl, new_children={cl[0]: ["CL01_C01", "CL01_C02"], cl[1]: ["CL02_C01"]})
check("chips created under chiplets", r.status_code == 200 and len(r.json()["created"]) == 3)

trav = api.get(f"/api/fab/wafers/{wid}/traveler").json()
check("3-level tree", sorted(u["sample_type"] for u in trav["units"]) == ["chip"] * 3 + ["chiplet"] * 2 + ["wafer"])
st = {s["id"]: s for s in trav["steps"]}
check("statuses + edits visible", st["rca_clean"]["status"] == "done" and st["wafer_trench"]["status"] == "skipped"
      and st["development"]["status"] == "pending" and st["rca_clean"]["records"][0]["edited_by"] == "Tim")

leaves = [u["unique_id"] for u in trav["units"] if u["is_leaf"]]
store["fail_link"] = {leaves[-1]}
r = step(wid, "jj_liftoff", leaves, rows={"nmp_1_hotplate": {"time_min": 90}})
check("partial link failure reported", r.status_code == 200 and not r.json()["success"] and len(r.json()["errors"]) == 1)
store["fail_link"] = set()

# Printing
check("printers listed", api.get("/api/fab/printers").json()["printers"][0]["printer_id"] == "b30-113")
check("bad printer id -> 400", api.post("/api/fab/print", json={"printer_id": "a/b#", "sample_id": wid}).status_code == 400)
r = api.post("/api/fab/print", json={"printer_id": "b30-113", "sample_id": wid})
check("print ok", r.json()["success"] and store["prints"][-1] == ("b30-113", wid, "QCMF_WFR_99"))
store["print_result"] = {"status": "timeout", "detail": "Printer b30-113 appears offline"}
r = api.post("/api/fab/print", json={"printer_id": "b30-113", "sample_id": wid})
check("print timeout surfaced", not r.json()["success"] and "offline" in r.json()["detail"])

check("synthesis fields still served", "Perovskites_10k" in api.get("/api/synthesis/fields").json()["categories"])

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f" -- FAILED: {', '.join(failed)}" if failed else ""))
sys.exit(1 if failed else 0)
