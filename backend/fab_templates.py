# Process flow templates for the fabrication traveler.
# Transcribed from the QCMF wafer traveler sheet (WFR_04). Only `parameters`
# are entered per run; `substeps` are copied into each record as-is.


def num(key, label, unit=None, default=None):
    return {"key": key, "label": label, "unit": unit, "type": "number", "default": default}


def text(key, label, default=None):
    return {"key": key, "label": label, "unit": None, "type": "text", "default": default}


def sub(process, **details):
    return {"process": process, **details}


DESCUM_SUBSTEPS = [
    sub("Load wafer"),
    sub("O2 descum", comment="strike + etch steps"),
    sub("Unload wafer"),
    sub("Chamber clean with cleaning wafer", time="30 mins", comment="Recipe name = CHAMBER CLEAN WITH WAFER"),
    sub("Microscope inspection"),
]

DESCUM_PARAMETERS = [
    text("recipe", "Recipe name", "YB_O2_Descum"),
    num("forward_power_w", "Forward power", "W", 30),
    num("icp_power_w", "ICP power", "W", 0),
    num("pressure_mtorr", "Pressure", "mTorr", 80),
    num("o2_flow_sccm", "O2 flow", "sccm", 100),
    num("etch_time_s", "Etch time (strike + etch)", "s", 25),
]

QCMF_QUBIT_V1_STEPS = [
    {
        "id": "rca_clean", "label": "Step 1A", "name": "Substrate cleaning (RCA)",
        "optional": False, "condition": {"wafer_type": "qubit"}, "tool": "Hotplate", "action": None,
        "substeps": [
            sub("RCA 1 clean", params="NH4OH:H2O2:H2O 1:1:5", tool="Hotplate",
                comment="20ml:20ml:100ml for 4 inch wafers. Pour NH4OH and DIW, bring to 90C, then add H2O2"),
            sub("DIW beaker 1", temp="RT", time="1 min"),
            sub("DIW beaker 2", temp="RT", time="1 min"),
            sub("DIW rinse", temp="RT", time="20 secs"),
            sub("N2 blow dry"),
        ],
        "parameters": [
            num("rca_temp_c", "RCA temperature", "C", 90),
            num("rca_time_min", "RCA time", "min", 20),
        ],
    },
    {
        "id": "solvent_clean", "label": "Step 1B", "name": "Substrate cleaning (solvents)",
        "optional": False, "condition": {"wafer_type": "test"}, "tool": "Sonicator", "action": None,
        "substeps": [
            sub("Acetone", temp="50C", time="5 mins", tool="Sonicator", specs="37kHz at 100% pwr"),
            sub("Acetone", temp="50C", time="5 mins", tool="Sonicator", specs="80kHz at 100% pwr"),
            sub("IPA", temp="50C", time="5 mins", tool="Sonicator", specs="80kHz at 100% pwr"),
            sub("IPA rinse and N2 dry"),
        ],
        "parameters": [
            num("acetone_temp_c", "Acetone temperature", "C", 50),
            num("acetone_time_min", "Acetone time (each bath)", "min", 5),
            num("ipa_time_min", "IPA time", "min", 5),
        ],
    },
    {
        "id": "native_oxide_removal", "label": "Step 2", "name": "Native oxide removal",
        "optional": False, "condition": None, "tool": "HF Bench", "action": None,
        "substeps": [
            sub("BOE dip", params="10:1 mixture", temp="RT", tool="HF Bench"),
            sub("DIW beaker 1", temp="RT", time="1 min", tool="HF Bench"),
            sub("DIW beaker 2", temp="RT", time="1 min", tool="HF Bench"),
            sub("IPA", temp="RT", time="30 secs", tool="Solvent bench"),
            sub("N2 blow dry", tool="Solvent bench"),
            sub("Transfer to glove box"),
        ],
        "parameters": [num("boe_time_s", "BOE dip time", "s", 60)],
    },
    {
        "id": "al_deposition", "label": "Step 3A", "name": "Al deposition (e-beam evaporation)",
        "optional": False, "condition": {"base_metal": "Al"}, "tool": "E-beam evaporator", "action": None,
        "substeps": [
            sub("Load wafer into loadlock"),
            sub("Precondition"), sub("Autotune"), sub("Stabilize"), sub("Deposit"), sub("Postcondition"),
        ],
        "parameters": [
            text("recipe", "Recipe name"),
            num("ox_chamber_pressure_torr", "Ox chamber pressure", "Torr"),
            num("evap_chamber_pressure_torr", "Evap chamber pressure", "Torr"),
            num("precondition_power_pct", "Precondition power", "%", 7),
            num("stability_factor", "Autotune stability factor", None, 2),
            num("rate_a_s", "Deposition rate", "A/s", 2),
            num("rate_accuracy_pct", "Rate accuracy", "%", 5),
            num("thickness_a", "Thickness", "A", 1000),
        ],
    },
    {
        "id": "nbn_deposition", "label": "Step 3B", "name": "NbN deposition (reactive sputtering)",
        "optional": False, "condition": {"base_metal": "NbN"}, "tool": "Sputter", "action": None,
        "substeps": [sub("Load wafer"), sub("NbN deposition"), sub("Unload wafer")],
        "parameters": [
            text("recipe", "Recipe name"),
            text("target", "Target"),
            num("deposition_temp_c", "Deposition temperature", "C"),
            num("ar_flow_sccm", "Ar flow", "sccm"),
            num("pressure_mtorr", "Pressure", "mTorr"),
            num("target_output_pct", "Target output", "%"),
            num("target_dc_bias_v", "Target DC bias", "V"),
            text("n2_flow_sccm", "N2 flow rate (min-max)"),
            num("calibrated_rate_a_s", "Calibrated rate", "A/s"),
            num("tooling_factor", "Tooling factor"),
            num("thickness_nm", "Thickness", "nm"),
            num("target_substrate_distance", "Target-substrate distance"),
        ],
    },
    {
        "id": "resist_spin", "label": "Step 4", "name": "Resist spinning",
        "optional": False, "condition": None, "tool": "CEE hotplate", "action": None,
        "substeps": [
            sub("Bake", tool="CEE hotplate", comment="Program 100C_180s"),
            sub("N2 blow dry", comment="After placing in spinner"),
            sub("Spincoat", specs="Program 9"),
            sub("Bake", tool="CEE hotplate", comment="Program 100C_180s"),
            sub("Clean up spinner"),
        ],
        "parameters": [
            text("resist", "Resist", "S1805"),
            num("spin_rpm", "Spin speed", "rpm", 6000),
            num("spin_time_s", "Spin time", "s", 45),
            num("bake_temp_c", "Bake temperature", "C", 100),
            num("bake_time_min", "Bake time", "min", 3),
        ],
    },
    {
        "id": "exposure", "label": "Step 5", "name": "Exposure",
        "optional": False, "condition": None, "tool": "MLA", "action": None,
        "substeps": [sub("Calibrate dose"), sub("Expose", tool="MLA", comment="Can vary based on the dose test")],
        "parameters": [
            num("dose_mj_cm2", "Dose", "mJ/cm2", 50),
            num("defocus", "Defocus", None, 4),
        ],
    },
    {
        "id": "development", "label": "Step 6", "name": "Development",
        "optional": False, "condition": None, "tool": "Acid bench", "action": None,
        "substeps": [
            sub("MF 26A", temp="RT", tool="Acid bench", comment="Strong agitation during development"),
            sub("DIW", temp="RT", time="30 sec"),
            sub("DIW rinse + N2 blow dry"),
            sub("Microscope inspection"),
        ],
        "parameters": [num("mf26a_time_s", "MF 26A time", "s", 30)],
    },
    {
        "id": "o2_descum", "label": "Step 7", "name": "O2 descum",
        "optional": False, "condition": None, "tool": "Oxford ICP chlorine", "action": None,
        "substeps": DESCUM_SUBSTEPS,
        "parameters": DESCUM_PARAMETERS,
    },
    {
        "id": "al_wet_etch", "label": "Step 8A", "name": "Wet etch (Al base metal)",
        "optional": False, "condition": {"base_metal": "Al"}, "tool": "Acid bench", "action": None,
        "substeps": [
            sub("Phosphoric acid / Al etchant", temp="RT", tool="Acid bench",
                comment="Etch rates vary based on thickness and sample size"),
            sub("DIW 1", time="2 mins", comment="Magnetic spinner at 600 rpm while rinsing"),
            sub("DIW 2", comment="Second beaker of fresh DIW"),
            sub("DIW rinse + N2 dry"),
        ],
        "parameters": [num("etch_time_min", "Etch time", "min", 7)],
    },
    {
        "id": "nbn_dry_etch", "label": "Step 8B", "name": "Dry etch (NbN base metal)",
        "optional": False, "condition": {"base_metal": "NbN"}, "tool": "Oxford ICP fluorine", "action": None,
        "substeps": [
            sub("Load wafer"), sub("CF4 etch", comment="Time calculated from etch rate and thickness"),
            sub("Unload wafer"),
            sub("Chamber clean with cleaning wafer", comment="Recipe name = CHAMBER CLEAN WITH WAFER"),
            sub("Microscope inspection"),
        ],
        "parameters": [
            text("recipe", "Recipe name", "MS_NbN etch"),
            num("forward_power_w", "Forward power", "W"),
            num("icp_power_w", "ICP power", "W"),
            num("pressure_mtorr", "Pressure", "mTorr"),
            num("cf4_flow_sccm", "CF4 flow", "sccm", 50),
            num("etch_time_s", "Etch time", "s"),
        ],
    },
    {
        # The sheet lists O2 descum values here; confirm the real trench recipe.
        "id": "wafer_trench", "label": "Step 9", "name": "Wafer trench (Al base metal)",
        "optional": False, "condition": {"base_metal": "Al"}, "tool": "Oxford ICP fluorine", "action": None,
        "substeps": [
            sub("Load wafer"), sub("Trench etch"), sub("Unload wafer"),
            sub("Chamber clean with cleaning wafer", time="30 mins"),
            sub("Microscope inspection"),
        ],
        "parameters": [
            text("recipe", "Recipe name", "OPT_CF4_etch"),
            num("forward_power_w", "Forward power", "W", 30),
            num("icp_power_w", "ICP power", "W", 0),
            num("pressure_mtorr", "Pressure", "mTorr", 80),
            num("gas_flow_sccm", "Gas flow", "sccm", 100),
            num("etch_time_s", "Etch time", "s", 25),
        ],
    },
    {
        "id": "resist_strip_qubit", "label": "Step 10A", "name": "Photoresist stripping (qubit)",
        "optional": False, "condition": {"wafer_type": "qubit"}, "tool": "Hotplate / Sonicator", "action": None,
        "substeps": [
            sub("NMP 1", tool="Hotplate"),
            sub("NMP 1", temp="65C", time="10 + 10 mins", tool="Sonicator", specs="37kHz + 80kHz at 50% pwr"),
            sub("NMP 2", temp="65C", time="5 mins", tool="Sonicator", specs="80kHz at 50% pwr",
                comment="New beaker of fresh NMP"),
            sub("IPA 1", temp="50C", time="5 mins", tool="Sonicator", specs="80kHz at 50% pwr"),
            sub("IPA 2", temp="50C", time="2 mins", tool="Hotplate"),
            sub("IPA rinse and N2 blow dry"),
        ],
        "parameters": [
            num("nmp_temp_c", "NMP hotplate temperature", "C", 80),
            num("nmp_time_min", "NMP hotplate time", "min", 20),
        ],
    },
    {
        "id": "resist_strip_test", "label": "Step 10B", "name": "Photoresist stripping (test)",
        "optional": False, "condition": {"wafer_type": "test"}, "tool": "Hotplate / Sonicator", "action": None,
        "substeps": [
            sub("NMP 1", tool="Hotplate"),
            sub("NMP 1", temp="65C", time="10 + 10 mins", tool="Sonicator", specs="37kHz + 80kHz at 50% pwr"),
            sub("IPA 1", temp="50C", time="5 mins", tool="Sonicator", specs="80kHz at 50% pwr"),
            sub("IPA rinse and N2 blow dry"),
        ],
        "parameters": [
            num("nmp_temp_c", "NMP hotplate temperature", "C", 80),
            num("nmp_time_min", "NMP hotplate time", "min", 20),
        ],
    },
    {
        "id": "jj_resist_spin", "label": "Step 11", "name": "JJ e-beam resist spin",
        "optional": False, "condition": None, "tool": "E-beam spinner / Oven", "action": None,
        "substeps": [
            sub("Dehydration bake", temp="100C", time="3 mins", tool="CEE hotplate", comment="Program 100C_180s"),
            sub("Wafer cooldown", time="1 min"),
            sub("Spincoat MMA", time="45 sec", tool="ebeam spinner", specs="Program 14"),
            sub("Bake", tool="Oven"),
            sub("Wafer cooldown", time="1 min"),
            sub("Spincoat PMMA C2", time="45 sec", tool="ebeam spinner", specs="Program 4"),
            sub("Bake", tool="Oven"),
            sub("Wafer cooldown", time="1 min"),
            sub("Clean spinner"),
        ],
        "parameters": [
            num("mma_rpm", "MMA spin speed", "rpm", 4000),
            num("pmma_rpm", "PMMA spin speed", "rpm", 1000),
            num("bake_temp_c", "Bake temperature", "C", 180),
            num("bake_time_min", "Bake time", "min", 5),
        ],
    },
    {
        "id": "jj_ebeam_exposure", "label": "Step 12", "name": "JJ e-beam exposure",
        "optional": False, "condition": None, "tool": "E-beam writer", "action": None,
        "substeps": [sub("JJ layer", params="Layer 2/0"), sub("Undercut layer", params="Layer 10/0")],
        "parameters": [
            num("base_dose_uc_cm2", "Base dose", "uC/cm2", 1100),
            num("undercut_dose_pct", "Undercut dose (% of base)", "%", 25),
        ],
    },
    {
        "id": "jj_development", "label": "Step 13", "name": "JJ development",
        "optional": False, "condition": None, "tool": "Solvent bench", "action": None,
        "substeps": [
            sub("MIBK:IPA 1:3", temp="RT", tool="Solvent bench", comment="Mild agitation"),
            sub("IPA", temp="RT", time="30 sec"),
            sub("IPA rinse", comment="Mildly using wash bottle"),
            sub("N2 blow dry"),
            sub("Microscope inspection"),
        ],
        "parameters": [num("mibk_ipa_time_s", "MIBK:IPA time", "s", 60)],
    },
    {
        "id": "cut_chiplets", "label": "Step 13b", "name": "Cut into chiplets",
        "optional": True, "condition": None, "tool": "Dicing saw", "action": "create_chiplets",
        "substeps": [sub("Cut wafer into chiplets")],
        "parameters": [],
    },
    {
        "id": "jj_o2_descum", "label": "Step 14", "name": "JJ O2 descum",
        "optional": False, "condition": None, "tool": "Oxford ICP chlorine", "action": None,
        "substeps": DESCUM_SUBSTEPS,
        "parameters": DESCUM_PARAMETERS,
    },
    {
        "id": "jj_native_oxide_removal", "label": "Step 15", "name": "JJ native oxide removal",
        "optional": True, "condition": None, "tool": "HF Bench", "action": None,
        "substeps": [
            sub("Al PAD etch 639", temp="RT", tool="HF Bench"),
            sub("DIW beaker 1", temp="RT", time="20 secs", tool="HF Bench"),
            sub("DIW beaker 2", temp="RT", time="20 secs", tool="HF Bench"),
            sub("DIW rinse", temp="RT", tool="HF Bench"),
            sub("N2 blow dry", tool="HF Bench"),
            sub("Transfer to glove box"),
        ],
        "parameters": [num("etch_time_s", "Etch time", "s", 10)],
    },
    {
        "id": "jj_deposition", "label": "Step 16", "name": "JJ deposition (pDolan)",
        "optional": False, "condition": None, "tool": "Plassys", "action": None,
        "substeps": [
            sub("Load wafer into loadlock", specs="With right orientation"),
            sub("Ar milling", comment="Subject to change with recipe"),
            sub("Ti gettering", specs="5% accuracy"),
            sub("Lead 1", specs="5% accuracy"),
            sub("Oxidation", comment="Subject to change with recipe"),
            sub("Ti gettering"),
            sub("Lead 2", specs="5% accuracy"),
            sub("Capping oxide"),
            sub("Unload wafer into loadlock"),
        ],
        "parameters": [
            text("sequence_name", "Sequence name"),
            num("ar_mill_voltage_v", "Ar mill acc. voltage", "V", 250),
            num("ar_mill_current_ma", "Ar mill current", "mA", 100),
            num("ar_mill_time_s", "Ar mill time", "s", 60),
            num("ti_getter1_nm", "Ti gettering 1 thickness", "nm", 35),
            num("lead1_tilt_deg", "Lead 1 tilt", "deg", 60),
            num("lead1_thickness_nm", "Lead 1 thickness", "nm", 60),
            num("oxidation_pressure_torr", "Oxidation pressure", "Torr", 15),
            num("oxidation_time_s", "Oxidation time", "s", 900),
            num("ti_getter2_nm", "Ti gettering 2 thickness", "nm", 35),
            num("lead2_tilt_deg", "Lead 2 tilt", "deg", 0),
            num("lead2_thickness_nm", "Lead 2 thickness", "nm", 70),
            num("capping_pressure_torr", "Capping oxide pressure", "Torr", 10),
            num("capping_time_s", "Capping oxide time", "s", 300),
            num("deposition_rate_a_s", "Deposition rate", "A/s", 2),
        ],
    },
    {
        "id": "predicing_resist", "label": "Step 17", "name": "Resist coating (pre-dicing)",
        "optional": False, "condition": None, "tool": "CEE hotplate", "action": None,
        "substeps": [
            sub("Spincoat", specs="Program 5", comment="No prebake to avoid heating JJs"),
            sub("Bake", tool="CEE hotplate"),
            sub("Clean up spinner"),
        ],
        "parameters": [
            text("resist", "Resist", "S1805"),
            num("spin_rpm", "Spin speed", "rpm", 2000),
            num("spin_time_s", "Spin time", "s", 45),
            num("bake_temp_c", "Bake temperature", "C", 100),
            num("bake_time_min", "Bake time", "min", 3),
        ],
    },
    {
        "id": "dicing", "label": "Step 18", "name": "Dicing into chips",
        "optional": False, "condition": None, "tool": "Dicing saw", "action": "create_chips",
        "substeps": [sub("Dicing")],
        "parameters": [text("dicing_location", "Dicing location", "Marvell")],
    },
    {
        "id": "jj_liftoff", "label": "Step 19", "name": "JJ liftoff",
        "optional": False, "condition": None, "tool": "Hotplate / Sonicator", "action": None,
        "substeps": [
            sub("NMP 1", tool="Hotplate", specs="Mild pipetting to remove metal",
                comment="Remove metal with pipette and transfer to waste"),
            sub("NMP 1", tool="Sonicator with double beaker", specs="80kHz at 30% pwr",
                comment="Same NMP beaker"),
            sub("IPA 1", temp="50C", time="10 mins", tool="Hotplate",
                comment="First rinse in another IPA beaker to remove excess NMP"),
            sub("IPA rinse and N2 blow dry"),
        ],
        "parameters": [
            num("nmp_temp_c", "NMP temperature", "C", 80),
            num("nmp_time_h", "NMP time", "h", 2),
            num("sonication_time_s", "Sonication time", "s", 15),
        ],
    },
    {
        "id": "jj_post_clean", "label": "Step 20", "name": "JJ post clean",
        "optional": True, "condition": None, "tool": None, "action": None,
        "substeps": [],
        "parameters": [],
    },
]

WAFER_SPEC_STEP = {
    "id": "wafer_spec", "label": "Step 0", "name": "Wafer specification",
    "optional": False, "condition": None, "tool": None, "action": None, "substeps": [],
    "parameters": [
        text("substrate_material", "Substrate material", "Silicon 001"),
        text("substrate_spec", "Substrate specification", "Res >20000 kOhm DSP 550um thick SSP"),
        text("batch_number", "Batch number"),
        text("gds_file", "GDS file name / link"),
    ],
}

FAB_TEMPLATES = {
    "QCMF_Qubit_v1": {
        "name": "QCMF qubit wafer",
        # Wafers go into their labeled box after this step.
        "label_after_step": "native_oxide_removal",
        "wafer_options": {
            "wafer_type": ["qubit", "test"],
            "base_metal": ["Al", "NbN"],
        },
        "wafer_spec": WAFER_SPEC_STEP,
        "steps": QCMF_QUBIT_V1_STEPS,
    },
}


def get_step(template_id, step_id):
    template = FAB_TEMPLATES[template_id]
    if step_id == WAFER_SPEC_STEP["id"]:
        return template["wafer_spec"]
    return next((s for s in template["steps"] if s["id"] == step_id), None)


def step_applies(step, wafer_options):
    condition = step.get("condition") or {}
    return all(wafer_options.get(k) == v for k, v in condition.items())
