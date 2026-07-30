"""
Initial FindingFrame taxonomy.

`GOAL.md` is the source of truth for the Phase A 20-class checklist. This
module also keeps aliases for earlier pivot-plan names so draft outputs can be
canonicalized before validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FindingTypeDefinition:
    finding_type: str
    display_name: str
    definition: str
    body_region_gate: tuple[str, ...]
    synonyms: tuple[str, ...]
    positive_examples: tuple[str, ...]
    negative_examples: tuple[str, ...]
    exclusion_rules: tuple[str, ...]

    def concept_terms(self) -> tuple[str, ...]:
        """Terms that can support this concept in evidence text."""
        base = self.finding_type.replace("_", " ")
        terms = (base, self.display_name, *self.synonyms)
        seen: set[str] = set()
        deduped: list[str] = []
        for term in terms:
            key = " ".join(term.lower().replace("_", " ").split())
            if key and key not in seen:
                seen.add(key)
                deduped.append(term)
        return tuple(deduped)


INITIAL_FINDING_TYPES: tuple[FindingTypeDefinition, ...] = (
    FindingTypeDefinition(
        finding_type="liver_metastasis",
        display_name="liver metastasis",
        definition="Metastatic disease involving liver or hepatic parenchyma.",
        body_region_gate=("abdomen", "liver", "hepatic", "pet_ct"),
        synonyms=("hepatic metastasis", "hepatic metastases", "liver mets"),
        positive_examples=("Multiple hepatic metastases are again seen.",),
        negative_examples=("No hepatic metastases.",),
        exclusion_rules=(
            "Do not use for simple hepatic cysts, hemangiomas, or nonspecific liver lesions unless metastasis is stated.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="lung_metastasis",
        display_name="lung metastasis",
        definition="Metastatic disease involving lung parenchyma.",
        body_region_gate=("chest", "lung", "thorax", "pet_ct"),
        synonyms=("pulmonary metastasis", "pulmonary metastases", "lung mets"),
        positive_examples=("Numerous bilateral pulmonary metastases have enlarged.",),
        negative_examples=("No pulmonary metastatic disease.",),
        exclusion_rules=(
            "Do not use for an isolated nonspecific nodule unless metastatic disease is stated.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="bone_metastasis",
        display_name="bone metastasis",
        definition="Metastatic disease involving osseous structures.",
        body_region_gate=("bone", "spine", "pelvis", "rib", "skull", "pet_ct"),
        synonyms=("osseous metastasis", "osseous metastases", "skeletal metastases"),
        positive_examples=("New sclerotic osseous metastasis in the right iliac bone.",),
        negative_examples=("No destructive osseous lesion.",),
        exclusion_rules=("Do not use for traumatic fracture unless metastasis is stated.",),
    ),
    FindingTypeDefinition(
        finding_type="brain_metastasis",
        display_name="brain metastasis",
        definition="Metastatic disease involving brain parenchyma or meninges.",
        body_region_gate=("brain", "head", "mri", "ct_head"),
        synonyms=("intracranial metastasis", "brain mets", "metastatic brain lesion"),
        positive_examples=("Enhancing lesions are suspicious for brain metastases.",),
        negative_examples=("No intracranial metastatic disease.",),
        exclusion_rules=(
            "Do not use for primary brain tumor, infarct, hemorrhage, or nonspecific white matter disease.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="lymph_node_metastasis",
        display_name="lymph node metastasis",
        definition="Metastatic or malignant nodal disease.",
        body_region_gate=("neck", "chest", "abdomen", "pelvis", "axilla", "groin"),
        synonyms=(
            "nodal metastasis",
            "metastatic lymph node",
            "malignant lymphadenopathy",
            "nodal disease",
            "adenopathy",
        ),
        positive_examples=("Bulky metastatic retroperitoneal lymphadenopathy has decreased.",),
        negative_examples=("No pathologic lymphadenopathy.",),
        exclusion_rules=(
            "Do not use for reactive or benign-appearing lymph nodes unless malignancy or metastasis is stated.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="pleural_effusion",
        display_name="pleural effusion",
        definition="Fluid in the pleural space.",
        body_region_gate=("chest", "pleura", "thorax"),
        synonyms=("pleural fluid", "effusion"),
        positive_examples=("Small bilateral pleural effusions are present.",),
        negative_examples=("No pleural effusion.",),
        exclusion_rules=("Do not use for pericardial effusion or ascites.",),
    ),
    FindingTypeDefinition(
        finding_type="ascites",
        display_name="ascites",
        definition="Free intraperitoneal fluid.",
        body_region_gate=("abdomen", "pelvis", "peritoneum"),
        synonyms=("free intraperitoneal fluid", "free abdominal fluid", "peritoneal fluid"),
        positive_examples=("Moderate volume ascites has increased.",),
        negative_examples=("No ascites.",),
        exclusion_rules=(
            "Do not use for pleural, pericardial, or localized postoperative fluid collections.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="bowel_obstruction",
        display_name="bowel obstruction",
        definition="Mechanical or functional obstruction of small or large bowel.",
        body_region_gate=("abdomen", "pelvis", "bowel", "gi"),
        synonyms=("small bowel obstruction", "large bowel obstruction", "transition point"),
        positive_examples=("Small bowel obstruction with transition point in the pelvis.",),
        negative_examples=("No bowel obstruction.",),
        exclusion_rules=("Do not use for ileus unless obstruction is stated or strongly suspected.",),
    ),
    FindingTypeDefinition(
        finding_type="pneumothorax",
        display_name="pneumothorax",
        definition="Air in the pleural space.",
        body_region_gate=("chest", "pleura", "thorax"),
        synonyms=("pleural air", "apical pneumothorax"),
        positive_examples=("Small right apical pneumothorax is unchanged.",),
        negative_examples=("No pneumothorax.",),
        exclusion_rules=("Do not use for pneumomediastinum or subcutaneous emphysema alone.",),
    ),
    FindingTypeDefinition(
        finding_type="pulmonary_embolism",
        display_name="pulmonary embolism",
        definition="Bland or tumor embolic material in the pulmonary arterial tree.",
        body_region_gate=("chest", "pulmonary_artery", "cta"),
        synonyms=(
            "pe",
            "pulmonary arterial embolus",
            "pulmonary emboli",
            "pulmonary tumor embolus",
            "pulmonary tumor thrombus",
        ),
        positive_examples=("Segmental pulmonary embolism in the right lower lobe.",),
        negative_examples=("No pulmonary embolism.",),
        exclusion_rules=(
            "Do not use for venous thrombosis outside the pulmonary arteries. If one statement spans venous tumor thrombus and pulmonary tumor embolus, emit both vascular finding types.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="deep_vein_thrombosis",
        display_name="deep vein thrombosis",
        definition="Bland or tumor thrombus in the deep venous system, including caval, portal, hepatic, or renal veins and contiguous right-atrial extension.",
        body_region_gate=(
            "extremity",
            "pelvis",
            "vein",
            "ultrasound",
            "abdomen",
            "inferior_vena_cava",
            "right_atrium",
        ),
        synonyms=(
            "dvt",
            "deep venous thrombosis",
            "venous thrombus",
            "tumor thrombus",
            "ivc thrombus",
            "hepatic vein thrombus",
            "portal vein tumor thrombus",
        ),
        positive_examples=("Occlusive DVT in the left femoral vein.",),
        negative_examples=("No deep venous thrombosis.",),
        exclusion_rules=(
            "Do not use for pulmonary embolism, superficial thrombophlebitis, isolated vascular encasement, or vascular invasion without explicit intraluminal thrombus/embolus. Do not emit primary_tumor for tumor thrombus alone unless the primary/local tumor is separately stated.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="pneumonia_or_infection",
        display_name="pneumonia or infection",
        definition="Radiographic pneumonia, infectious consolidation, abscess, or infectious inflammatory process.",
        body_region_gate=("chest", "lung", "abdomen", "soft_tissue"),
        synonyms=("pneumonia", "infection", "infectious consolidation", "abscess"),
        positive_examples=("Right lower lobe consolidation concerning for pneumonia.",),
        negative_examples=("No evidence of pneumonia.",),
        exclusion_rules=("Do not use for sterile atelectasis or edema unless infection is stated.",),
    ),
    FindingTypeDefinition(
        finding_type="hemorrhage",
        display_name="hemorrhage",
        definition="Bleeding, hematoma, or blood products in any body region.",
        body_region_gate=("brain", "abdomen", "pelvis", "soft_tissue", "body_wall"),
        synonyms=("hematoma", "bleeding", "blood products", "intracranial hemorrhage"),
        positive_examples=("Small right subdural hematoma is unchanged.",),
        negative_examples=("No acute intracranial hemorrhage.",),
        exclusion_rules=("Do not use for simple fluid without blood products.",),
    ),
    FindingTypeDefinition(
        finding_type="hydronephrosis",
        display_name="hydronephrosis",
        definition="Dilation of the renal collecting system.",
        body_region_gate=("kidney", "renal", "abdomen", "pelvis"),
        synonyms=("renal collecting system dilation", "hydroureteronephrosis"),
        positive_examples=("Moderate left hydronephrosis has developed.",),
        negative_examples=("No hydronephrosis.",),
        exclusion_rules=(
            "Do not use for simple renal cysts or non-obstructing calculi without collecting system dilation.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="fracture",
        display_name="fracture",
        definition="Acute, subacute, chronic, traumatic, pathologic, or insufficiency fracture.",
        body_region_gate=("bone", "spine", "extremity", "rib", "pelvis", "skull"),
        synonyms=("broken bone", "compression deformity", "pathologic fracture"),
        positive_examples=("Acute right posterior sixth rib fracture.",),
        negative_examples=("No acute fracture.",),
        exclusion_rules=("Do not use for degenerative change without fracture.",),
    ),
    FindingTypeDefinition(
        finding_type="primary_tumor",
        display_name="primary tumor",
        definition="Index malignancy, dominant known cancer, local recurrence, or primary tumor bed finding.",
        body_region_gate=("any",),
        synonyms=(
            "primary malignancy",
            "primary cancer",
            "tumor recurrence",
            "local recurrence",
            "dominant mass",
        ),
        positive_examples=("Irregular right breast mass corresponding to known primary tumor.",),
        negative_examples=("No evidence of local recurrence.",),
        exclusion_rules=(
            "Do not use for metastatic lesions unless they represent local primary-site recurrence or the report calls it the primary tumor.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="hepatomegaly",
        display_name="hepatomegaly",
        definition="Enlargement of the liver.",
        body_region_gate=("abdomen", "liver", "hepatic"),
        synonyms=("enlarged liver", "hepatic enlargement"),
        positive_examples=("Mild hepatomegaly is present.",),
        negative_examples=("No hepatomegaly.",),
        exclusion_rules=("Do not use for focal liver lesions or liver metastases.",),
    ),
    FindingTypeDefinition(
        finding_type="post_surgical_change",
        display_name="post surgical change",
        definition="Expected or notable postoperative anatomy, resection, hardware, clips, or post-treatment change.",
        body_region_gate=("any",),
        synonyms=("postoperative change", "postsurgical change", "status post", "resection cavity"),
        positive_examples=("Postsurgical changes of left upper lobectomy.",),
        negative_examples=("No postoperative collection.",),
        exclusion_rules=("Do not use for active tumor recurrence unless recurrence is separately stated.",),
    ),
    FindingTypeDefinition(
        finding_type="device_or_line",
        display_name="device or line",
        definition="Medical device, catheter, tube, line, stent, drain, pacer, or hardware position.",
        body_region_gate=("any",),
        synonyms=("central line", "endotracheal tube", "picc", "port catheter", "stent", "drain"),
        positive_examples=("Right IJ central line tip terminates in the SVC.",),
        negative_examples=("No retained radiopaque foreign body.",),
        exclusion_rules=("Do not use for surgical clips unless clinically relevant or explicitly discussed.",),
    ),
    FindingTypeDefinition(
        finding_type="cardiomegaly",
        display_name="cardiomegaly",
        definition="Enlargement of the cardiac silhouette or heart.",
        body_region_gate=("chest", "heart", "cardiac"),
        synonyms=("enlarged cardiac silhouette", "cardiac enlargement", "enlarged heart"),
        positive_examples=("Mild cardiomegaly is unchanged.",),
        negative_examples=("No cardiomegaly.",),
        exclusion_rules=("Do not use for pericardial effusion or coronary calcification alone.",),
    ),
)

INITIAL_ECHO_FINDING_TYPES: tuple[FindingTypeDefinition, ...] = (
    FindingTypeDefinition(
        finding_type="lv_systolic_function",
        display_name="LV systolic function",
        definition="Left ventricular systolic function assessment, including LVEF and qualitative grading.",
        body_region_gate=("heart", "left_ventricle", "echo"),
        synonyms=("lv systolic function", "left ventricular systolic function", "lvef", "ejection fraction", "systolic function", "lv function"),
        positive_examples=("LVEF is estimated at 55%.", "Normal left ventricular systolic function."),
        negative_examples=("LVEF could not be assessed.",),
        exclusion_rules=(
            "Do not use for RV function or diastolic function assessment.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="lv_diastolic_function",
        display_name="LV diastolic function",
        definition="Left ventricular diastolic function grading, E/A ratio, E/e', LA pressure, or filling pattern.",
        body_region_gate=("heart", "left_ventricle", "echo"),
        synonyms=("lv diastolic function", "diastolic function", "diastolic dysfunction", "diastolic filling", "e/a ratio", "e/e'"),
        positive_examples=("Grade I diastolic dysfunction with impaired relaxation.",),
        negative_examples=("Diastolic function could not be assessed.",),
        exclusion_rules=("Do not use for systolic function findings.",),
    ),
    FindingTypeDefinition(
        finding_type="lv_size",
        display_name="LV size",
        definition="Left ventricular chamber dimensions including LVEDD, LVESD, and wall thickness.",
        body_region_gate=("heart", "left_ventricle", "echo"),
        synonyms=("lv size", "lv dimensions", "lv internal dimension", "lvidd", "lvedd", "lvesd", "lv end-diastolic", "lv end-systolic", "septal wall thickness", "posterior wall thickness"),
        positive_examples=("LV internal diastolic dimension is 4.8 cm.", "Normal LV cavity size."),
        negative_examples=("LV dimensions are not reported.",),
        exclusion_rules=("Do not use for RV, LA, or RA size.",),
    ),
    FindingTypeDefinition(
        finding_type="rv_function",
        display_name="RV systolic function",
        definition="Right ventricular systolic function assessment including TAPSE, fractional area change, and qualitative grading.",
        body_region_gate=("heart", "right_ventricle", "echo"),
        synonyms=("rv function", "rv systolic function", "right ventricular function", "tapse", "rv fac"),
        positive_examples=("TAPSE measures 22 mm indicating normal RV systolic function.", "Mildly reduced RV systolic function."),
        negative_examples=("RV is not well visualized.",),
        exclusion_rules=("Do not use for LV function findings.",),
    ),
    FindingTypeDefinition(
        finding_type="rv_size",
        display_name="RV size",
        definition="Right ventricular chamber size assessment including RV basal diameter.",
        body_region_gate=("heart", "right_ventricle", "echo"),
        synonyms=("rv size", "rv dimensions", "rv basal diameter", "rv enlargement", "right ventricular enlargement"),
        positive_examples=("The right ventricle is normal in size.", "Mildly dilated right ventricle with basal diameter 4.2 cm."),
        negative_examples=("RV is not well visualized.",),
        exclusion_rules=("Do not use for LV, LA, or RA size.",),
    ),
    FindingTypeDefinition(
        finding_type="la_size",
        display_name="LA size",
        definition="Left atrial size including LA diameter, LA volume index, and qualitative grading.",
        body_region_gate=("heart", "left_atrium", "echo"),
        synonyms=("la size", "left atrial size", "la volume", "la volume index", "la diameter", "left atrial enlargement", "left atrial dilation"),
        positive_examples=("Left atrium is mildly dilated with LA volume index 38 mL/m2.", "Normal LA size."),
        negative_examples=("LA is not well visualized.",),
        exclusion_rules=("Do not use for LV, RV, or RA size.",),
    ),
    FindingTypeDefinition(
        finding_type="ra_size",
        display_name="RA size",
        definition="Right atrial size including RA area, RA pressure estimate, and qualitative grading.",
        body_region_gate=("heart", "right_atrium", "echo"),
        synonyms=("ra size", "right atrial size", "ra area", "ra pressure", "ra enlargement", "right atrial enlargement", "right atrial dilation"),
        positive_examples=("Right atrium is mildly dilated.", "Normal RA size with RA area 16 cm2."),
        negative_examples=("RA is not well visualized.",),
        exclusion_rules=("Do not use for LV, RV, or LA size.",),
    ),
    FindingTypeDefinition(
        finding_type="aortic_stenosis",
        display_name="aortic stenosis",
        definition="Aortic valve stenosis severity assessment including peak velocity, mean gradient, and aortic valve area (AVA).",
        body_region_gate=("heart", "aortic_valve", "echo"),
        synonyms=("aortic stenosis", "as", "aortic valve stenosis", "aortic sclerosis", "aortic valve sclerosis"),
        positive_examples=("Mild aortic stenosis with peak velocity 2.5 m/s, mean gradient 12 mmHg.", "Moderate aortic stenosis. AVA 1.2 cm2."),
        negative_examples=("No aortic stenosis.", "Aortic valve is normal with no stenosis."),
        exclusion_rules=("Do not use for aortic regurgitation or mitral disease.",),
    ),
    FindingTypeDefinition(
        finding_type="aortic_regurgitation",
        display_name="aortic regurgitation",
        definition="Aortic valve regurgitation severity including jet width, vena contracta, pressure half-time, and qualitative grading.",
        body_region_gate=("heart", "aortic_valve", "echo"),
        synonyms=("aortic regurgitation", "ar", "aortic insufficiency", "ai"),
        positive_examples=("Mild aortic regurgitation is present.", "Moderate aortic insufficiency with holodiastolic flow reversal."),
        negative_examples=("No aortic regurgitation.", "Trace aortic regurgitation considered physiologic."),
        exclusion_rules=("Do not use for aortic stenosis or mitral disease. Trace/physiologic regurgitation in a normal valve may be excluded.",),
    ),
    FindingTypeDefinition(
        finding_type="mitral_regurgitation",
        display_name="mitral regurgitation",
        definition="Mitral valve regurgitation severity including EROA, regurgitant volume, vena contracta, and qualitative grading.",
        body_region_gate=("heart", "mitral_valve", "echo"),
        synonyms=("mitral regurgitation", "mr", "mitral insufficiency", "mi"),
        positive_examples=("Mild-to-moderate mitral regurgitation with EROA 0.20 cm2.", "Severe mitral regurgitation with flail leaflet."),
        negative_examples=("No mitral regurgitation.", "Trace mitral regurgitation considered physiologic."),
        exclusion_rules=("Do not use for mitral stenosis or aortic valve disease. Trace/physiologic regurgitation in a normal valve may be excluded.",),
    ),
    FindingTypeDefinition(
        finding_type="mitral_stenosis",
        display_name="mitral stenosis",
        definition="Mitral valve stenosis severity including mean gradient, mitral valve area (MVA), and pressure half-time.",
        body_region_gate=("heart", "mitral_valve", "echo"),
        synonyms=("mitral stenosis", "ms", "mitral valve stenosis", "rheumatic mitral stenosis"),
        positive_examples=("Moderate mitral stenosis with mean gradient 8 mmHg, MVA 1.4 cm2.", "Mild mitral stenosis."),
        negative_examples=("No mitral stenosis.", "Mitral valve is structurally normal."),
        exclusion_rules=("Do not use for mitral regurgitation or aortic disease.",),
    ),
    FindingTypeDefinition(
        finding_type="tricuspid_regurgitation",
        display_name="tricuspid regurgitation",
        definition="Tricuspid valve regurgitation severity including TR velocity and estimated RVSP/PASP.",
        body_region_gate=("heart", "tricuspid_valve", "echo"),
        synonyms=("tricuspid regurgitation", "tr", "tricuspid insufficiency", "ti", "tr velocity", "rvsp", "pasp"),
        positive_examples=("Mild tricuspid regurgitation with TR velocity 2.8 m/s. Estimated RVSP 36 mmHg.", "Moderate tricuspid regurgitation."),
        negative_examples=("No tricuspid regurgitation.", "Trace tricuspid regurgitation considered physiologic."),
        exclusion_rules=("Do not use for pulmonic valve disease. Trace/physiologic TR may be excluded.",),
    ),
    FindingTypeDefinition(
        finding_type="pericardial_effusion",
        display_name="pericardial effusion",
        definition="Pericardial fluid collection including size grading and hemodynamic significance.",
        body_region_gate=("heart", "pericardium", "echo"),
        synonyms=("pericardial effusion", "pericardial fluid", "pericardial tamponade", "effusion"),
        positive_examples=("Small circumferential pericardial effusion without tamponade.", "Moderate pericardial effusion with right atrial collapse."),
        negative_examples=("No pericardial effusion.",),
        exclusion_rules=("Do not use for pleural effusion or ascites.",),
    ),
    FindingTypeDefinition(
        finding_type="wall_motion_abnormality",
        display_name="wall motion abnormality",
        definition="Regional wall motion abnormality including hypokinesis, akinesis, dyskinesis, and segmental assessment.",
        body_region_gate=("heart", "left_ventricle", "echo"),
        synonyms=("wall motion abnormality", "rwma", "segmental wall motion", "hypokinesis", "akinesis", "dyskinesis", "regional wall motion abnormality"),
        positive_examples=("Hypokinesis of the inferolateral wall.", "Akinesis of the apical segments with apical thrombus."),
        negative_examples=("No regional wall motion abnormalities.", "Normal segmental wall motion."),
        exclusion_rules=("Do not use for global systolic function reduction unless localized wall motion is specified.",),
    ),
    FindingTypeDefinition(
        finding_type="ivc_size",
        display_name="IVC size",
        definition="Inferior vena cava diameter and collapsibility assessment for right atrial pressure estimation.",
        body_region_gate=("heart", "ivc", "abdomen", "echo"),
        synonyms=("ivc diameter", "ivc collapsibility", "inferior vena cava size", "ivc size", "ivc respiratory variation"),
        positive_examples=("IVC diameter 1.9 cm with <50% collapse, suggesting elevated RA pressure.", "Normal IVC size with >50% respiratory collapse."),
        negative_examples=("IVC is not well visualized.",),
        exclusion_rules=("Do not use for aortic or venous measurements outside the IVC.",),
    ),
)

TAXONOMY_BY_TYPE: dict[str, FindingTypeDefinition] = {
    item.finding_type: item for item in INITIAL_FINDING_TYPES
}

ECHO_TAXONOMY_BY_TYPE: dict[str, FindingTypeDefinition] = {
    item.finding_type: item for item in INITIAL_ECHO_FINDING_TYPES
}

TAXONOMY_ALIASES: dict[str, str] = {
    "metastasis_liver": "liver_metastasis",
    "metastasis_lung": "lung_metastasis",
    "metastasis_bone": "bone_metastasis",
    "metastasis_brain": "brain_metastasis",
    "lymphadenopathy": "lymph_node_metastasis",
    "frature": "fracture",
    "frctures": "fracture",
}

ANATOMY_ALIASES: dict[str, str] = {
    "brain": "intracranial",
    "intracranial": "intracranial",
    "cerebral": "intracranial",
    "cerebellar": "intracranial",
    "head": "intracranial",
    "ct_head": "intracranial",
    "chest": "thorax",
    "thorax": "thorax",
    "thoracic": "thorax",
    "hemithorax": "thorax",
    "right_chest": "thorax",
    "left_chest": "thorax",
    "right_hemithorax": "thorax",
    "left_hemithorax": "thorax",
    "lung": "thorax",
    "lungs": "thorax",
    "right_lung": "thorax",
    "left_lung": "thorax",
    "bilateral_lungs": "thorax",
    "lung_parenchyma": "thorax",
    "pulmonary_parenchyma": "thorax",
    "rib": "rib",
    "ribs": "rib",
    "right_rib": "rib",
    "left_rib": "rib",
    "posterior_rib": "rib",
    "rib_six": "rib",
    "sixth_rib": "rib",
    "rib_6": "rib",
    "right_sixth_rib": "rib",
    "posterior_sixth_rib": "rib",
    "right_posterior_sixth_rib": "rib",
    "right_femoral_head": "femur",
    "left_femoral_head": "femur",
    "bilateral_femoral_heads": "femur",
    "right_breast": "breast",
    "left_breast": "breast",
    "bilateral_breasts": "breast",
    "gallbladder_fossa": "gallbladder",
    "bone": "bone",
    "bones": "bone",
    "osseous": "bone",
    "skeletal": "bone",
    "skeleton": "bone",
    "musculoskeletal": "bone",
    "cervical_spine": "spine",
    "thoracic_spine": "spine",
    "lumbar_spine": "spine",
    "lumbosacral_spine": "spine",
    "right_lateral_malleolus": "lateral_malleolus",
    "left_lateral_malleolus": "lateral_malleolus",
    "distal_fibula": "lateral_malleolus",
    "right_distal_fibula": "lateral_malleolus",
    "left_distal_fibula": "lateral_malleolus",
    "fibula": "lateral_malleolus",
    "right_fibula": "lateral_malleolus",
    "left_fibula": "lateral_malleolus",
    "right_hemithorax_pleura": "thorax",
    "left_hemithorax_pleura": "thorax",
    "right_pleura": "thorax",
    "left_pleura": "thorax",
    "pleural_cavity": "thorax",
    "right_pleural_cavity": "thorax",
    "left_pleural_cavity": "thorax",
    "left_lower_extremity_veins": "deep_vein",
    "right_lower_extremity_veins": "deep_vein",
    "lower_extremity_veins": "deep_vein",
    "aorta_iliac_arteries": "aorta",
    "aortoiliac": "aorta",
    "aorto_iliac": "aorta",
    "common_iliac_arteries": "aorta",
    "femoral_arteries": "femoral_region",
    "femoral_region": "femoral_region",
    "kidneys": "kidney",
    "kidney_collecting_system": "kidney",
    "renal_collecting_system": "kidney",
    "retroperitoneum": "abdomen",
    "retroperitoneal": "abdomen",
    "retroperitoneal_lymph_nodes": "abdomen",
    "mesentery": "abdomen",
    "mesenteric": "abdomen",
    "mesenteric_lymph_nodes": "abdomen",
    "pelvic_lymph_nodes": "pelvis",
    "inguinal_lymph_nodes": "pelvis",
    "mediastinum": "thorax",
    "mediastinal": "thorax",
    "mediastinal_lymph_nodes": "thorax",
    "precarinal_lymph_node": "thorax",
    "tracheoesophageal_lymph_node": "thorax",
    "abdomen": "abdomen",
    "abdominal": "abdomen",
    "pelvis": "pelvis",
    "pelvic": "pelvis",
    "peritoneal_cavity": "peritoneum",
    "intraperitoneal_space": "peritoneum",
    "abdominal_cavity": "peritoneum",
    "urinary_bladder": "bladder",
    "salivary_glands": "salivary_gland",
    "pectoral_region": "thorax",
    "right_pectoral_region": "thorax",
    "left_pectoral_region": "thorax",
    "cavoatrial_junction": "thorax",
}

_PULMONARY_LOBE_RE = re.compile(
    r"^(?:(?:right|left|bilateral)_)?(?:upper|middle|lower)_lobe$"
)

EVIDENCE_SUPPORT_TERMS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "ascites": (
        "free fluid",
        "free abdominal fluid",
        "free gas or fluid",
        "free air or fluid",
        "intraperitoneal fluid",
    ),
    "cardiomegaly": (
        "heart size",
        "cardiac silhouette",
        "cardiomediastinal silhouette",
        "borderline enlarged",
        "borderline enlargement",
    ),
    "fracture": (
        "osseous abnormality",
        "osseous abnormalities",
        "fracture or dislocation",
        "fractures or dislocations",
        "bony abnormality",
        "bony abnormalities",
    ),
    "hydronephrosis": (
        "collecting system dilation",
        "renal collecting system",
        "renal pelvis dilation",
    ),
    "liver_metastasis": (
        "hepatic and pulmonary metastases",
        "hepatic hypodensities",
        "hepatic lesions",
        "hepatic lesion",
        "liver lesion",
        "liver lesions",
        "suspicious hepatic lesion",
        "suspicious hepatic lesions",
        "suspicious for metastasis",
        "suspicious for metastases",
    ),
    "lung_metastasis": (
        "hepatic and pulmonary metastases",
        "pulmonary nodules",
        "metastatic nodules",
    ),
    "bone_metastasis": (
        "osseous lesion",
        "osseous lesions",
        "suspicious osseous lesion",
        "suspicious osseous lesions",
        "lytic lesion",
        "lytic lesions",
        "lucent lesion",
        "lucent lesions",
        "destructive osseous lesion",
        "destructive osseous lesions",
    ),
    "lymph_node_metastasis": (
        "lymphadenopathy",
        "adenopathy",
        "lymph node enlargement",
        "enlarged lymph nodes",
        "pathologic lymph nodes",
        "pathologically enlarged lymph nodes",
        "nodal disease",
        "malignant involvement",
    ),
    "primary_tumor": (
        "adenocarcinoma",
        "carcinoma",
        "neoplasm",
        "malignancy",
        "malignant mass",
        "neoplastic nodule",
        "tumor bed",
        "mural thickening",
        "known cancer",
    ),
    "deep_vein_thrombosis": (
        "tumor thrombus",
        "venous thrombus",
        "embolus burden",
        "ivc thrombus",
        "inferior vena cava thrombus",
    ),
    "pneumonia_or_infection": (
        "infectious process",
        "consolidation",
    ),
    "post_surgical_change": (
        "status post",
        "post operative",
        "post-operative",
        "post surgical",
        "post-surgical",
        "surgical clips",
    ),
}


def _normalize_anatomy_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def canonicalize_anatomy(anatomy: Any) -> str:
    """Normalize coarse anatomy labels used by frame gold and metrics."""
    normalized = _normalize_anatomy_text(anatomy)
    if not normalized:
        return "unknown"
    alias = ANATOMY_ALIASES.get(normalized)
    if alias:
        return alias

    tokens = set(normalized.split("_"))
    if "rib" in tokens or "ribs" in tokens:
        return "rib"
    # Bone/joint normalizations: map specific bone terms to canonical anatomy.
    if tokens & {"tibia", "tibial", "tibial_plateau"} or "tibial_plateau" in normalized:
        return "tibia"
    if tokens & {"femur", "femoral"}:
        return "femur"
    if tokens & {"fibula", "fibular"}:
        return "fibula"
    if tokens & {"patella", "patellar"}:
        return "patella"
    if tokens & {"knee", "knees"}:
        return "knee"
    if tokens & {"hip", "hips"}:
        if "left" in tokens:
            return "left_hip"
        if "right" in tokens:
            return "right_hip"
        return "hip"
    if tokens & {"ankle", "ankles"}:
        return "ankle"
    if tokens & {"shoulder", "shoulders"}:
        return "shoulder"
    if tokens & {"elbow", "elbows"}:
        return "elbow"
    if tokens & {"wrist", "wrists"}:
        return "wrist"
    if tokens & {"humerus", "humeral"}:
        return "humerus"
    if tokens & {"clavicle", "clavicular"}:
        return "clavicle"
    if tokens & {"scapula", "scapular"}:
        return "scapula"
    if tokens & {"radius", "radial"}:
        return "radius"
    if tokens & {"ulna", "ulnar"}:
        return "ulna"
    if tokens & {"brain", "intracranial", "cerebral", "cerebellar", "cerebellum", "meninges", "meningioma", "temporoparietal", "pachymeninges"}:
        return "intracranial"
    # "Head" is also an anatomic subregion of long bones (for example,
    # femoral or humeral head), so only use it as a cranial synonym after
    # the specific bone rules above have had a chance to match.
    if "head" in tokens and "neck" not in tokens:
        return "intracranial"
    if (
        tokens & {"chest", "thorax", "thoracic", "lung", "lungs"}
        or normalized.endswith("_hemithorax")
        or _PULMONARY_LOBE_RE.match(normalized)
    ):
        return "thorax"
    if tokens & {"abdomen", "abdominal"}:
        return "abdomen"
    if tokens & {"pelvis", "pelvic", "iliac"}:
        return "pelvis"
    return normalized


def canonicalize_finding_type(finding_type: str) -> str:
    normalized = str(finding_type or "").strip().lower()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return TAXONOMY_ALIASES.get(normalized, normalized)


def all_finding_types() -> tuple[str, ...]:
    return tuple(TAXONOMY_BY_TYPE.keys())


def is_taxonomy_finding_type(finding_type: str) -> bool:
    canonical = canonicalize_finding_type(finding_type)
    return (
        canonical in TAXONOMY_BY_TYPE
        or canonicalize_echo_finding_type(finding_type) in ECHO_TAXONOMY_BY_TYPE
        or is_cxr_taxonomy_finding_type(finding_type)
    )


def get_finding_type_definition(finding_type: str) -> FindingTypeDefinition | None:
    canonical = canonicalize_finding_type(finding_type)
    definition = TAXONOMY_BY_TYPE.get(canonical)
    if definition is not None:
        return definition
    echo_definition = ECHO_TAXONOMY_BY_TYPE.get(canonicalize_echo_finding_type(finding_type))
    if echo_definition is not None:
        return echo_definition
    return get_cxr_finding_type_definition(finding_type)


def concept_terms_for_type(finding_type: str) -> tuple[str, ...]:
    definition = get_finding_type_definition(finding_type)
    if definition is None:
        return (canonicalize_finding_type(finding_type).replace("_", " "),)
    return definition.concept_terms()


def evidence_terms_for_type(finding_type: str) -> tuple[str, ...]:
    """Terms allowed to support evidence-gate concept checks."""
    canonical = canonicalize_finding_type(finding_type)
    if canonical in TAXONOMY_BY_TYPE:
        terms = [
            *concept_terms_for_type(canonical),
            *EVIDENCE_SUPPORT_TERMS_BY_TYPE.get(canonical, ()),
        ]
    elif is_cxr_taxonomy_finding_type(finding_type):
        terms = list(cxr_evidence_terms_for_type(finding_type))
    else:
        echo_canonical = canonicalize_echo_finding_type(finding_type)
        terms = [
            *echo_concept_terms_for_type(echo_canonical),
            *ECHO_EVIDENCE_SUPPORT_TERMS_BY_TYPE.get(echo_canonical, ()),
        ]
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        key = " ".join(str(term).lower().replace("_", " ").split())
        if key and key not in seen:
            seen.add(key)
            deduped.append(term)
    return tuple(deduped)


def taxonomy_prompt_block() -> str:
    """Compact taxonomy block for LLM prompts."""
    lines: list[str] = []
    for item in INITIAL_FINDING_TYPES:
        lines.append(f"- {item.finding_type}: {item.definition}")
        lines.append(f"  body_region_gate: {', '.join(item.body_region_gate)}")
        lines.append(f"  synonyms: {', '.join(item.synonyms)}")
        lines.append(f"  exclusions: {' '.join(item.exclusion_rules)}")
    return "\n".join(lines)


# Oncology taxonomy tables and canonicalization logic that determine
# FindingFrame track identity (composite key = finding_type | anatomy |
# laterality). Consulted by extraction/rule_layer_provenance.py to fingerprint
# the rule layer for run-artifact provenance (see docs/REMEDIATION_PLAN_2026-07-29.md
# P2-2). The echo/CXR taxonomies below belong to a separate pipeline and are
# intentionally excluded. Keep this registry in sync when adding, removing, or
# renaming a table or function with real behavioral effect on oncology anatomy
# or finding-type identity.
ONCOLOGY_RULE_TABLES: dict[str, Any] = {
    "INITIAL_FINDING_TYPES": INITIAL_FINDING_TYPES,
    "TAXONOMY_ALIASES": TAXONOMY_ALIASES,
    "ANATOMY_ALIASES": ANATOMY_ALIASES,
}
ONCOLOGY_RULE_LOGIC_FUNCTIONS: tuple[Any, ...] = (
    _normalize_anatomy_text,
    canonicalize_anatomy,
    canonicalize_finding_type,
)


ECHO_ANATOMY_ALIASES: dict[str, str] = {
    "heart": "heart",
    "cardiac": "heart",
    "lv": "left_ventricle",
    "l_v": "left_ventricle",
    "left_ventricle": "left_ventricle",
    "left_ventricular": "left_ventricle",
    "rv": "right_ventricle",
    "r_v": "right_ventricle",
    "right_ventricle": "right_ventricle",
    "right_ventricular": "right_ventricle",
    "la": "left_atrium",
    "l_a": "left_atrium",
    "left_atrium": "left_atrium",
    "left_atrial": "left_atrium",
    "ra": "right_atrium",
    "r_a": "right_atrium",
    "right_atrium": "right_atrium",
    "right_atrial": "right_atrium",
    "aortic_valve": "aortic_valve",
    "av": "aortic_valve",
    "aortic": "aortic_valve",
    "aov": "aortic_valve",
    "mitral_valve": "mitral_valve",
    "mv": "mitral_valve",
    "mitral": "mitral_valve",
    "m_valve": "mitral_valve",
    "tricuspid_valve": "tricuspid_valve",
    "tv": "tricuspid_valve",
    "tricuspid": "tricuspid_valve",
    "t_valve": "tricuspid_valve",
    "pulmonic_valve": "pulmonic_valve",
    "pv": "pulmonic_valve",
    "pulmonic": "pulmonic_valve",
    "p_valve": "pulmonic_valve",
    "pericardial_space": "pericardial_space",
    "pericardium": "pericardial_space",
    "pericardial": "pericardial_space",
    "pericardial_sac": "pericardial_space",
    "ivc": "ivc",
    "inferior_vena_cava": "ivc",
    "vena_cava": "ivc",
}

ECHO_EVIDENCE_SUPPORT_TERMS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "lv_systolic_function": (
        "visually estimated ef",
        "ejection fraction",
        "lvef",
        "systolic performance",
        "contractility",
    ),
    "lv_diastolic_function": (
        "diastolic filling",
        "e/a",
        "e/e'",
        "e/e prime",
        "deceleration time",
        "dt",
        "isovolumic relaxation time",
    ),
    "lv_size": (
        "end diastolic dimension",
        "end systolic dimension",
        "septal wall",
        "posterior wall",
        "relative wall thickness",
        "lv mass",
    ),
    "rv_function": (
        "tapse",
        "fractional area change",
        "s'",
        "s prime",
        "tricuspid annular plane systolic excursion",
    ),
    "rv_size": (
        "basal diameter",
        "mid cavity",
        "longitudinal dimension",
        "proximal rvot",
    ),
    "la_size": (
        "volume index",
        "lavi",
        "ap diameter",
        "medial-lateral dimension",
    ),
    "ra_size": (
        "area",
        "volume",
        "minor axis",
        "major axis",
    ),
    "aortic_stenosis": (
        "peak velocity",
        "mean gradient",
        "aortic valve area",
        "ava",
        "vmax",
        "velocity ratio",
        "dimensionless index",
    ),
    "aortic_regurgitation": (
        "jet width",
        "vena contracta",
        "pressure half-time",
        "pht",
        "holodiastolic flow reversal",
        "regurgitant volume",
        "regurgitant fraction",
    ),
    "mitral_regurgitation": (
        "eroa",
        "effective regurgitant orifice",
        "regurgitant volume",
        "rvol",
        "vena contracta",
        "proximal isovelocity surface area",
        "pisa",
    ),
    "mitral_stenosis": (
        "mean gradient",
        "mitral valve area",
        "mva",
        "pressure half-time",
        "pht",
        "planimetry",
    ),
    "tricuspid_regurgitation": (
        "tr peak velocity",
        "tr vmax",
        "estimated rvsp",
        "estimated pasp",
        "right ventricular systolic pressure",
        "pulmonary artery systolic pressure",
    ),
    "pericardial_effusion": (
        "effusion",
        "pericardial fluid",
        "tamponade",
        "right atrial collapse",
        "right ventricular collapse",
        "respiratory variation",
    ),
    "wall_motion_abnormality": (
        "hypokinesis",
        "akinesis",
        "dyskinesis",
        "segmental wall motion",
        "regional wall motion",
        "wall thickening",
    ),
    "ivc_size": (
        "collapsibility",
        "respiratory collapse",
        "sniff",
        "ivc diameter",
        "caval index",
    ),
}

ECHO_TAXONOMY_ALIASES: dict[str, str] = {
    "lv_function": "lv_systolic_function",
    "lv_systolic_dysfunction": "lv_systolic_function",
    "ejection_fraction": "lv_systolic_function",
    "lvef": "lv_systolic_function",
    "lv_diastolic_dysfunction": "lv_diastolic_function",
    "diastolic_dysfunction": "lv_diastolic_function",
    "lv_dimensions": "lv_size",
    "lv_mass": "lv_size",
    "rv_dysfunction": "rv_function",
    "rv_failure": "rv_function",
    "rv_dilation": "rv_size",
    "rv_enlargement": "rv_size",
    "la_enlargement": "la_size",
    "la_dilation": "la_size",
    "ra_enlargement": "ra_size",
    "ra_dilation": "ra_size",
    "aortic_insufficiency": "aortic_regurgitation",
    "ar": "aortic_regurgitation",
    "ai": "aortic_regurgitation",
    "as": "aortic_stenosis",
    "mitral_insufficiency": "mitral_regurgitation",
    "mr": "mitral_regurgitation",
    "mi": "mitral_regurgitation",
    "ms": "mitral_stenosis",
    "tricuspid_insufficiency": "tricuspid_regurgitation",
    "tr": "tricuspid_regurgitation",
    "pericardial_tamponade": "pericardial_effusion",
    "pericardial_fluid": "pericardial_effusion",
    "rwma": "wall_motion_abnormality",
    "segmental_wall_motion_abnormality": "wall_motion_abnormality",
    "inferior_vena_cava": "ivc_size",
    "ivc_collapsibility": "ivc_size",
    "ivc_diameter": "ivc_size",
}


def is_echo_taxonomy_finding_type(finding_type: str) -> bool:
    return canonicalize_echo_finding_type(finding_type) in ECHO_TAXONOMY_BY_TYPE


def canonicalize_echo_finding_type(finding_type: str) -> str:
    normalized = str(finding_type or "").strip().lower()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return ECHO_TAXONOMY_ALIASES.get(normalized, normalized)


def get_echo_finding_type_definition(finding_type: str) -> FindingTypeDefinition | None:
    return ECHO_TAXONOMY_BY_TYPE.get(canonicalize_echo_finding_type(finding_type))


def echo_concept_terms_for_type(finding_type: str) -> tuple[str, ...]:
    definition = get_echo_finding_type_definition(finding_type)
    if definition is None:
        return (canonicalize_echo_finding_type(finding_type).replace("_", " "),)
    return definition.concept_terms()


def echo_evidence_terms_for_type(finding_type: str) -> tuple[str, ...]:
    canonical = canonicalize_echo_finding_type(finding_type)
    terms = [
        *echo_concept_terms_for_type(canonical),
        *ECHO_EVIDENCE_SUPPORT_TERMS_BY_TYPE.get(canonical, ()),
    ]
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        key = " ".join(str(term).lower().replace("_", " ").split())
        if key and key not in seen:
            seen.add(key)
            deduped.append(term)
    return tuple(deduped)


def canonicalize_echo_anatomy(anatomy: Any) -> str:
    normalized = _normalize_anatomy_text(anatomy)
    if not normalized:
        return "unknown"
    alias = ECHO_ANATOMY_ALIASES.get(normalized)
    if alias:
        return alias
    tokens = set(normalized.split("_"))
    if tokens & {"ventricle", "ventricular"}:
        if tokens & {"left", "lv"}:
            return "left_ventricle"
        if tokens & {"right", "rv"}:
            return "right_ventricle"
        return "left_ventricle"
    if tokens & {"atrium", "atrial"}:
        if tokens & {"left", "la"}:
            return "left_atrium"
        if tokens & {"right", "ra"}:
            return "right_atrium"
        return "left_atrium"
    if "valve" in tokens or "valvular" in tokens or "root" in tokens or "leaflet" in tokens:
        if tokens & {"aortic", "av", "aov"} or "aortic" in normalized:
            return "aortic_valve"
        if tokens & {"mitral", "mv"}:
            return "mitral_valve"
        if tokens & {"tricuspid", "tv"}:
            return "tricuspid_valve"
        if tokens & {"pulmonic", "pv", "pulmonary"}:
            return "pulmonic_valve"
        if "aortic" in normalized:
            return "aortic_valve"
        return "aortic_valve"
    return normalized


def all_echo_finding_types() -> tuple[str, ...]:
    return tuple(ECHO_TAXONOMY_BY_TYPE.keys())


def echo_taxonomy_prompt_block() -> str:
    """Compact echo taxonomy block for LLM prompts."""
    lines: list[str] = []
    for item in INITIAL_ECHO_FINDING_TYPES:
        lines.append(f"- {item.finding_type}: {item.definition}")
        lines.append(f"  body_region_gate: {', '.join(item.body_region_gate)}")
        lines.append(f"  synonyms: {', '.join(item.synonyms)}")
        lines.append(f"  exclusions: {' '.join(item.exclusion_rules)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CXR (chest radiograph) domain taxonomy  [domain="cxr"]
# ---------------------------------------------------------------------------
# Native-vocabulary taxonomy used to externally validate the FindingFrame
# architecture on chest X-ray gold (RadGraph2, Chest ImaGenome). Canonical types
# are the union of Chest ImaGenome's 70 native label_names and RadGraph2 OBS
# head-findings, snake_cased, with the rare tail folded via CXR_TAXONOMY_ALIASES
# and the study-level normal/abnormal flags excluded. See
# evaluation/external/PLAN.md §7b and evaluation/external/label_crosswalk.json.

INITIAL_CXR_FINDING_TYPES: tuple[FindingTypeDefinition, ...] = (
    FindingTypeDefinition(
        finding_type="lung_opacity",
        display_name="lung opacity",
        definition="Nonspecific increased pulmonary opacity not further specified as consolidation, mass, or edema.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("airspace opacity", "opacification", "infiltrate", "increased density"),
        positive_examples=("There is a patchy opacity in the right lower lobe.",),
        negative_examples=("The lungs are clear without focal opacity.",),
        exclusion_rules=(
            "Use consolidation when air bronchograms or dense airspace filling is described; use pulmonary_edema for an edema pattern.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="consolidation",
        display_name="consolidation",
        definition="Dense airspace opacification, often with air bronchograms, indicating alveolar filling.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("airspace consolidation", "air bronchograms", "dense airspace opacity"),
        positive_examples=("Dense consolidation in the left lower lobe with air bronchograms.",),
        negative_examples=("No focal consolidation.",),
        exclusion_rules=("Use lung_opacity for nonspecific/hazy opacity without dense airspace filling.",),
    ),
    FindingTypeDefinition(
        finding_type="pneumonia",
        display_name="pneumonia",
        definition="Radiographic findings attributed to pulmonary infection.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("infectious infiltrate", "infection", "pneumonic consolidation"),
        positive_examples=("Findings compatible with right lower lobe pneumonia.",),
        negative_examples=("No evidence of pneumonia.",),
        exclusion_rules=("Use consolidation/lung_opacity for the imaging pattern when infection is not asserted.",),
    ),
    FindingTypeDefinition(
        finding_type="atelectasis",
        display_name="atelectasis",
        definition="Loss of lung volume from alveolar collapse; commonly linear, subsegmental, or plate-like.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("subsegmental atelectasis", "linear atelectasis", "plate-like atelectasis", "volume loss"),
        positive_examples=("Bibasilar linear atelectasis.",),
        negative_examples=("No atelectasis.",),
        exclusion_rules=("Use lung_collapse for lobar/segmental collapse with substantial volume loss.",),
    ),
    FindingTypeDefinition(
        finding_type="lung_collapse",
        display_name="lobar/segmental collapse",
        definition="Lobar or segmental lung collapse with substantial volume loss.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("lobar collapse", "segmental collapse", "whole-lung collapse"),
        positive_examples=("Near-complete collapse of the left lower lobe.",),
        negative_examples=("No lobar collapse.",),
        exclusion_rules=("Use atelectasis for minor/linear volume loss.",),
    ),
    FindingTypeDefinition(
        finding_type="aspiration",
        display_name="aspiration",
        definition="Radiographic findings suggesting aspirated material, typically dependent airspace opacity.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("aspiration pneumonitis", "aspiration changes"),
        positive_examples=("Dependent opacities concerning for aspiration.",),
        negative_examples=("No findings to suggest aspiration.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="copd_emphysema",
        display_name="COPD/emphysema",
        definition="Hyperexpansion and parenchymal changes of COPD or emphysema, including bullae.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("emphysema", "copd", "bullous disease", "cyst/bullae"),
        positive_examples=("Hyperinflated lungs with upper-lobe predominant emphysema.",),
        negative_examples=("No emphysematous change.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="interstitial_lung_disease",
        display_name="interstitial lung disease",
        definition="Reticular/interstitial markings suggesting interstitial lung disease.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("reticular markings", "ild pattern", "interstitial markings", "reticulonodular pattern"),
        positive_examples=("Increased reticular markings suggesting interstitial lung disease.",),
        negative_examples=("No interstitial abnormality.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="hyperaeration",
        display_name="hyperaeration",
        definition="Increased lung volumes / hyperinflation.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("hyperinflation", "hyperexpansion"),
        positive_examples=("The lungs are hyperinflated.",),
        negative_examples=("Normal lung volumes.",),
        exclusion_rules=("Distinct from copd_emphysema unless emphysematous change is stated.",),
    ),
    FindingTypeDefinition(
        finding_type="low_lung_volumes",
        display_name="low lung volumes",
        definition="Reduced lung volumes; a technical/positional assessment.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("low lung volumes", "poor inspiration", "low inspiratory volumes"),
        positive_examples=("Low lung volumes limit evaluation.",),
        negative_examples=("Adequate inspiratory volumes.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="lung_cancer",
        display_name="lung cancer",
        definition="Radiographic findings attributed to primary lung malignancy.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("bronchogenic carcinoma", "lung malignancy", "lung neoplasm"),
        positive_examples=("Spiculated mass concerning for lung cancer.",),
        negative_examples=("No suspicious pulmonary mass.",),
        exclusion_rules=("Use lung_lesion/pulmonary_nodule for the imaging finding when malignancy is not asserted.",),
    ),
    FindingTypeDefinition(
        finding_type="granulomatous_disease",
        display_name="granulomatous disease",
        definition="Findings of granulomatous disease (e.g., calcified granulomas, sarcoid pattern).",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("granuloma", "calcified granuloma", "sarcoidosis"),
        positive_examples=("Calcified granulomas consistent with prior granulomatous disease.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="lung_lesion",
        display_name="lung lesion",
        definition="A focal pulmonary lesion or mass not otherwise specified.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("lung mass", "pulmonary lesion", "mass"),
        positive_examples=("Left upper lobe mass.",),
        negative_examples=("No focal lung lesion.",),
        exclusion_rules=("Use pulmonary_nodule for discrete rounded nodules.",),
    ),
    FindingTypeDefinition(
        finding_type="pulmonary_nodule",
        display_name="pulmonary nodule",
        definition="One or more discrete rounded pulmonary nodules, including calcified nodules.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("nodule", "pulmonary nodules", "calcified nodule", "mass/nodule"),
        positive_examples=("A 6 mm nodule in the right upper lobe.",),
        negative_examples=("No pulmonary nodules.",),
        exclusion_rules=("Use lung_lesion for larger/ill-defined masses.",),
    ),
    FindingTypeDefinition(
        finding_type="bone_lesion",
        display_name="bone lesion",
        definition="Focal osseous lesion (lytic or sclerotic) of a rib, the spine, or another visualized bone.",
        body_region_gate=("chest", "thorax", "bone", "spine", "rib", "cxr"),
        synonyms=("osseous lesion", "sclerotic lesion", "lytic lesion", "bony lesion"),
        positive_examples=("Sclerotic lesion in the right humeral head.",),
        negative_examples=("No aggressive osseous lesion.",),
        exclusion_rules=(
            "Use the fracture types for fractures; use spinal_degenerative_changes for degenerative/arthritic change.",
        ),
    ),
    FindingTypeDefinition(
        finding_type="pleural_effusion",
        display_name="pleural effusion",
        definition="Fluid in the pleural space.",
        body_region_gate=("chest", "thorax", "pleura", "cxr"),
        synonyms=("effusion", "pleural fluid", "effusions"),
        positive_examples=("Moderate right pleural effusion.",),
        negative_examples=("No pleural effusion.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="pulmonary_edema",
        display_name="pulmonary edema",
        definition="Interstitial or alveolar pulmonary edema, including the hazy-opacity pattern of edema.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("edema", "hazy opacity", "interstitial edema", "alveolar edema"),
        positive_examples=("Mild pulmonary edema.",),
        negative_examples=("No pulmonary edema.",),
        exclusion_rules=("Use vascular_congestion for congestion/redistribution short of frank edema.",),
    ),
    FindingTypeDefinition(
        finding_type="vascular_congestion",
        display_name="vascular congestion",
        definition="Pulmonary vascular congestion, redistribution, or fluid overload short of frank edema.",
        body_region_gate=("chest", "thorax", "lung", "cxr"),
        synonyms=("vascular redistribution", "fluid overload", "cephalization", "congestive changes"),
        positive_examples=("Pulmonary vascular congestion.",),
        negative_examples=("No vascular congestion.",),
        exclusion_rules=("Use pulmonary_edema when interstitial/alveolar edema is stated.",),
    ),
    FindingTypeDefinition(
        finding_type="pneumothorax",
        display_name="pneumothorax",
        definition="Air in the pleural space.",
        body_region_gate=("chest", "thorax", "pleura", "cxr"),
        synonyms=("ptx",),
        positive_examples=("Small right apical pneumothorax.",),
        negative_examples=("No pneumothorax.",),
        exclusion_rules=("Use hydropneumothorax when an air-fluid level is described.",),
    ),
    FindingTypeDefinition(
        finding_type="hydropneumothorax",
        display_name="hydropneumothorax",
        definition="Combined air and fluid in the pleural space (air-fluid level).",
        body_region_gate=("chest", "thorax", "pleura", "cxr"),
        synonyms=("pyopneumothorax", "air-fluid level in pleural space"),
        positive_examples=("Hydropneumothorax with an air-fluid level in the right hemithorax.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="costophrenic_angle_blunting",
        display_name="costophrenic angle blunting",
        definition="Blunting of the costophrenic angle, often from a small effusion or scarring.",
        body_region_gate=("chest", "thorax", "pleura", "cxr"),
        synonyms=("blunted costophrenic angle", "cp angle blunting"),
        positive_examples=("Blunting of the left costophrenic angle.",),
        negative_examples=("Costophrenic angles are sharp.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="pleural_parenchymal_scarring",
        display_name="pleural/parenchymal scarring",
        definition="Chronic pleural or parenchymal scarring.",
        body_region_gate=("chest", "thorax", "pleura", "lung", "cxr"),
        synonyms=("scarring", "pleural thickening", "parenchymal scar", "fibrotic scarring"),
        positive_examples=("Biapical pleural-parenchymal scarring.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="pneumomediastinum",
        display_name="pneumomediastinum",
        definition="Air within the mediastinum.",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("mediastinal air",),
        positive_examples=("Pneumomediastinum is present.",),
        negative_examples=("No pneumomediastinum.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="subcutaneous_air",
        display_name="subcutaneous air",
        definition="Air within the soft tissues / subcutaneous emphysema.",
        body_region_gate=("chest", "thorax", "soft_tissue", "cxr"),
        synonyms=("subcutaneous emphysema", "soft tissue air"),
        positive_examples=("Subcutaneous emphysema along the right chest wall.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="sub_diaphragmatic_air",
        display_name="sub-diaphragmatic air",
        definition="Free air beneath the diaphragm.",
        body_region_gate=("chest", "abdomen", "thorax", "cxr"),
        synonyms=("pneumoperitoneum", "free intraperitoneal air", "subdiaphragmatic air"),
        positive_examples=("Free air under the right hemidiaphragm.",),
        negative_examples=("No free subdiaphragmatic air.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="enlarged_cardiac_silhouette",
        display_name="enlarged cardiac silhouette",
        definition="Enlargement of the cardiac silhouette (cardiomegaly).",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("cardiomegaly", "enlarged heart", "cardiac enlargement"),
        positive_examples=("The cardiac silhouette is enlarged.",),
        negative_examples=("Normal heart size.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="mediastinal_widening",
        display_name="mediastinal widening",
        definition="Widening of the mediastinal contour.",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("widened mediastinum",),
        positive_examples=("The mediastinum is widened.",),
        negative_examples=("Normal mediastinal contour.",),
        exclusion_rules=("Use superior_mediastinal_enlargement for a focal superior mediastinal mass.",),
    ),
    FindingTypeDefinition(
        finding_type="mediastinal_displacement",
        display_name="mediastinal displacement",
        definition="Shift or displacement of the mediastinum.",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("mediastinal shift", "tracheal deviation"),
        positive_examples=("Rightward mediastinal shift.",),
        negative_examples=("Midline mediastinum.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="superior_mediastinal_enlargement",
        display_name="superior mediastinal mass/enlargement",
        definition="Superior mediastinal mass or enlargement, including goiter.",
        body_region_gate=("chest", "thorax", "mediastinum", "neck", "cxr"),
        synonyms=("superior mediastinal mass", "mediastinal mass", "goiter"),
        positive_examples=("Superior mediastinal widening/mass.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="enlarged_hilum",
        display_name="enlarged hilum",
        definition="Enlargement of one or both hilar contours.",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("hilar enlargement", "hilar fullness", "hilar prominence", "enlarged hila"),
        positive_examples=("Enlarged right hilum.",),
        negative_examples=("Normal hilar contours.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="tortuous_aorta",
        display_name="tortuous aorta",
        definition="Tortuosity, unfolding, or ectasia of the thoracic aorta.",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("unfolded aorta", "aortic ectasia", "ectatic aorta"),
        positive_examples=("Tortuous thoracic aorta.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="vascular_calcification",
        display_name="vascular calcification",
        definition="Calcification of the aorta or other thoracic vessels.",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("aortic calcification", "calcified aorta", "vascular calcifications"),
        positive_examples=("Aortic arch calcification.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="pericardial_effusion",
        display_name="pericardial effusion",
        definition="Fluid within the pericardial space as inferred on chest radiograph.",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("pericardial fluid",),
        positive_examples=("Enlarging cardiac silhouette suggesting pericardial effusion.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="hernia",
        display_name="hernia",
        definition="Diaphragmatic or hiatal hernia.",
        body_region_gate=("chest", "abdomen", "thorax", "cxr"),
        synonyms=("hiatal hernia", "diaphragmatic hernia"),
        positive_examples=("Large hiatal hernia.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="elevated_hemidiaphragm",
        display_name="elevated hemidiaphragm",
        definition="Elevation of a hemidiaphragm.",
        body_region_gate=("chest", "thorax", "cxr"),
        synonyms=("diaphragmatic elevation", "raised hemidiaphragm"),
        positive_examples=("Elevated right hemidiaphragm.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="rib_fracture",
        display_name="rib fracture",
        definition="Fracture of one or more ribs.",
        body_region_gate=("chest", "thorax", "rib", "bone", "cxr"),
        synonyms=("rib fractures",),
        positive_examples=("Acute right posterior rib fractures.",),
        negative_examples=("No rib fracture.",),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="clavicle_fracture",
        display_name="clavicle fracture",
        definition="Fracture of the clavicle.",
        body_region_gate=("chest", "thorax", "clavicle", "bone", "cxr"),
        synonyms=("clavicular fracture",),
        positive_examples=("Mildly displaced left clavicle fracture.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="spinal_fracture",
        display_name="spinal fracture",
        definition="Fracture or compression deformity of a vertebral body.",
        body_region_gate=("chest", "thorax", "spine", "bone", "cxr"),
        synonyms=("vertebral fracture", "compression fracture"),
        positive_examples=("Compression fracture of a mid-thoracic vertebral body.",),
        negative_examples=(),
        exclusion_rules=("Use spinal_degenerative_changes for chronic degenerative change without fracture.",),
    ),
    FindingTypeDefinition(
        finding_type="spinal_degenerative_changes",
        display_name="spinal degenerative changes",
        definition="Degenerative changes of the spine.",
        body_region_gate=("chest", "thorax", "spine", "bone", "cxr"),
        synonyms=("degenerative disc disease", "spondylosis", "osteophytes", "degenerative changes"),
        positive_examples=("Degenerative changes of the thoracic spine.",),
        negative_examples=(),
        exclusion_rules=("Use scoliosis for lateral spinal curvature.",),
    ),
    FindingTypeDefinition(
        finding_type="scoliosis",
        display_name="scoliosis",
        definition="Lateral curvature of the spine (a structural deformity, not a degenerative change).",
        body_region_gate=("chest", "thorax", "spine", "bone", "cxr"),
        synonyms=("spinal curvature", "levoscoliosis", "dextroscoliosis", "kyphoscoliosis"),
        positive_examples=("Thoracolumbar dextroscoliosis.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="endotracheal_tube",
        display_name="endotracheal tube",
        definition="Endotracheal tube, typically described relative to the carina.",
        body_region_gate=("chest", "thorax", "trachea", "cxr"),
        synonyms=("ett", "et tube", "endotracheal tube"),
        positive_examples=("ET tube tip 4 cm above the carina.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="enteric_tube",
        display_name="enteric tube",
        definition="Enteric / nasogastric / orogastric / feeding tube.",
        body_region_gate=("chest", "abdomen", "thorax", "cxr"),
        synonyms=("ng tube", "nasogastric tube", "og tube", "feeding tube", "dobhoff"),
        positive_examples=("Enteric tube tip in the stomach.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="chest_tube",
        display_name="chest tube",
        definition="Pleural chest tube or mediastinal drain.",
        body_region_gate=("chest", "thorax", "pleura", "cxr"),
        synonyms=("pleural drain", "chest drain", "pigtail catheter", "mediastinal drain"),
        positive_examples=("Right pleural chest tube in place.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="central_venous_line",
        display_name="central venous line",
        definition="Central venous catheter (IJ, subclavian, PICC, Swan-Ganz, or port).",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("central line", "ij line", "picc", "subclavian line", "swan-ganz catheter", "chest port", "cvc"),
        positive_examples=("Right IJ central line tip in the SVC.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="cardiac_device",
        display_name="cardiac device",
        definition="Implanted cardiac device or surgical cardiac hardware (pacer, ICD, wires, CABG grafts, prosthetic valve).",
        body_region_gate=("chest", "thorax", "mediastinum", "cxr"),
        synonyms=("pacemaker", "pacer", "icd", "defibrillator", "sternal wires", "cabg grafts", "prosthetic valve"),
        positive_examples=("Left-sided dual-lead pacemaker.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
    FindingTypeDefinition(
        finding_type="other_support_device",
        display_name="other support device",
        definition="Other support device or hardware not otherwise categorized (e.g., IABP, tracheostomy tube).",
        body_region_gate=("chest", "thorax", "cxr"),
        synonyms=("intra-aortic balloon pump", "iabp", "tracheostomy tube", "support device", "hardware"),
        positive_examples=("Intra-aortic balloon pump tip in the proximal descending aorta.",),
        negative_examples=(),
        exclusion_rules=(),
    ),
)

CXR_TAXONOMY_BY_TYPE: dict[str, FindingTypeDefinition] = {
    item.finding_type: item for item in INITIAL_CXR_FINDING_TYPES
}

# snake_cased alias -> canonical CXR finding_type. Covers LLM-emitted variants
# and simple gold labels. The messy raw Chest ImaGenome label_names are mapped
# by the adapter via evaluation/external/label_crosswalk.json.
CXR_TAXONOMY_ALIASES: dict[str, str] = {
    "cardiomegaly": "enlarged_cardiac_silhouette",
    "enlarged_heart": "enlarged_cardiac_silhouette",
    "cardiac_enlargement": "enlarged_cardiac_silhouette",
    "airspace_opacity": "lung_opacity",
    "opacification": "lung_opacity",
    "infiltrate": "lung_opacity",
    "infiltration": "lung_opacity",
    "opacity": "lung_opacity",
    "opacities": "lung_opacity",
    "effusion": "pleural_effusion",
    "effusions": "pleural_effusion",
    "pleural_fluid": "pleural_effusion",
    "edema": "pulmonary_edema",
    "hazy_opacity": "pulmonary_edema",
    "interstitial_edema": "pulmonary_edema",
    "alveolar_edema": "pulmonary_edema",
    "fluid_overload": "vascular_congestion",
    "vascular_redistribution": "vascular_congestion",
    "congestion": "vascular_congestion",
    "cephalization": "vascular_congestion",
    "nodule": "pulmonary_nodule",
    "nodules": "pulmonary_nodule",
    "calcified_nodule": "pulmonary_nodule",
    "mass": "lung_lesion",
    "lung_mass": "lung_lesion",
    "ptx": "pneumothorax",
    "ett": "endotracheal_tube",
    "et_tube": "endotracheal_tube",
    "ng_tube": "enteric_tube",
    "nasogastric_tube": "enteric_tube",
    "og_tube": "enteric_tube",
    "orogastric_tube": "enteric_tube",
    "feeding_tube": "enteric_tube",
    "dobhoff": "enteric_tube",
    "ij_line": "central_venous_line",
    "picc": "central_venous_line",
    "picc_line": "central_venous_line",
    "subclavian_line": "central_venous_line",
    "swan_ganz_catheter": "central_venous_line",
    "chest_port": "central_venous_line",
    "cvc": "central_venous_line",
    "central_line": "central_venous_line",
    "pacemaker": "cardiac_device",
    "pacer": "cardiac_device",
    "icd": "cardiac_device",
    "defibrillator": "cardiac_device",
    "sternal_wires": "cardiac_device",
    "cabg_grafts": "cardiac_device",
    "prosthetic_valve": "cardiac_device",
    "iabp": "other_support_device",
    "intra_aortic_balloon_pump": "other_support_device",
    "tracheostomy_tube": "other_support_device",
    "lobar_collapse": "lung_collapse",
    "segmental_collapse": "lung_collapse",
    "volume_loss": "atelectasis",
    "linear_atelectasis": "atelectasis",
    "plate_like_atelectasis": "atelectasis",
    "subsegmental_atelectasis": "atelectasis",
    "emphysema": "copd_emphysema",
    "copd": "copd_emphysema",
    "bullae": "copd_emphysema",
    "hyperinflation": "hyperaeration",
    "hyperexpansion": "hyperaeration",
    "reticular_markings": "interstitial_lung_disease",
    "ild": "interstitial_lung_disease",
    "scarring": "pleural_parenchymal_scarring",
    "pleural_thickening": "pleural_parenchymal_scarring",
    "hiatal_hernia": "hernia",
    "diaphragmatic_hernia": "hernia",
    "widened_mediastinum": "mediastinal_widening",
    "mediastinal_shift": "mediastinal_displacement",
    "tracheal_deviation": "mediastinal_displacement",
    "mediastinal_mass": "superior_mediastinal_enlargement",
    "goiter": "superior_mediastinal_enlargement",
    "hilar_enlargement": "enlarged_hilum",
    "hilar_prominence": "enlarged_hilum",
    "unfolded_aorta": "tortuous_aorta",
    "aortic_ectasia": "tortuous_aorta",
    "aortic_calcification": "vascular_calcification",
    "pneumoperitoneum": "sub_diaphragmatic_air",
    "free_air": "sub_diaphragmatic_air",
    "subcutaneous_emphysema": "subcutaneous_air",
    "vertebral_fracture": "spinal_fracture",
    "compression_fracture": "spinal_fracture",
    "clavicular_fracture": "clavicle_fracture",
    "degenerative_changes": "spinal_degenerative_changes",
    "spondylosis": "spinal_degenerative_changes",
    "pericardial_fluid": "pericardial_effusion",
    "bronchogenic_carcinoma": "lung_cancer",
    "lung_malignancy": "lung_cancer",
    # RadGraph2 free-text OBS heads observed in the test split
    "infection": "pneumonia",
    "catheter": "central_venous_line",
    "sternotomy": "cardiac_device",
    "sternotomy_wires": "cardiac_device",
    "wires": "cardiac_device",
    "clips": "other_support_device",
    "surgical_clips": "other_support_device",
    "tube": "other_support_device",
    "tubes": "other_support_device",
    "line": "central_venous_line",
    "lines": "central_venous_line",
    "tortuous": "tortuous_aorta",
    "unfolding": "tortuous_aorta",
    "thickening": "pleural_parenchymal_scarring",
    "scar": "pleural_parenchymal_scarring",
    "scarring": "pleural_parenchymal_scarring",
    "degenerative": "spinal_degenerative_changes",
    "spondylosis": "spinal_degenerative_changes",
    "blunting": "costophrenic_angle_blunting",
    "calcification": "vascular_calcification",
    "calcifications": "vascular_calcification",
    "calcified": "vascular_calcification",
    "infiltrate": "lung_opacity",
    "infiltrates": "lung_opacity",
    "opacities": "lung_opacity",
    "hyperinflated": "hyperaeration",
    "hyperexpanded": "hyperaeration",
    "deviation": "mediastinal_displacement",
    "fracture": "rib_fracture",
    "fractures": "rib_fracture",
    "effusions": "pleural_effusion",
    "nodules": "pulmonary_nodule",
}

# CXR anatomy normalization. Chest ImaGenome bbox names carry laterality/zone
# qualifiers (e.g. "right upper lung zone"); this reduces them to a core region.
# Laterality is parsed separately by the adapter, not here.
CXR_ANATOMY_ALIASES: dict[str, str] = {
    "lung": "lung",
    "lungs": "lung",
    "cardiac_silhouette": "cardiac_silhouette",
    "heart": "cardiac_silhouette",
    "mediastinum": "mediastinum",
    "upper_mediastinum": "mediastinum",
    "aortic_arch": "aorta",
    "aorta": "aorta",
    "carina": "trachea",
    "trachea": "trachea",
    "svc": "svc",
    "cavoatrial_junction": "svc",
    "right_atrium": "cardiac_silhouette",
    "spine": "spine",
    "abdomen": "abdomen",
    "neck": "neck",
}

# Optional evidence-support terms beyond concept terms (mirrors echo).
CXR_EVIDENCE_SUPPORT_TERMS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "enlarged_cardiac_silhouette": (
        "heart size", "cardiac silhouette", "cardiac contour",
        "cardiomediastinal silhouette", "cardiomediastinal",
    ),
    "pleural_effusion": ("blunting", "meniscus", "layering"),
    "pneumothorax": ("visceral pleural line", "lucency", "deep sulcus"),
    "pulmonary_edema": ("kerley", "perihilar", "vascular"),
    "endotracheal_tube": ("carina", "tip"),
    "enteric_tube": ("stomach", "tip", "gastroesophageal"),
    "central_venous_line": ("svc", "cavoatrial", "tip"),
}


def is_cxr_taxonomy_finding_type(finding_type: str) -> bool:
    return canonicalize_cxr_finding_type(finding_type) in CXR_TAXONOMY_BY_TYPE


def canonicalize_cxr_finding_type(finding_type: str) -> str:
    normalized = str(finding_type or "").strip().lower()
    normalized = normalized.replace("-", "_").replace("/", "_").replace(" ", "_")
    normalized = "_".join(tok for tok in normalized.split("_") if tok)
    return CXR_TAXONOMY_ALIASES.get(normalized, normalized)


def get_cxr_finding_type_definition(finding_type: str) -> FindingTypeDefinition | None:
    return CXR_TAXONOMY_BY_TYPE.get(canonicalize_cxr_finding_type(finding_type))


def cxr_concept_terms_for_type(finding_type: str) -> tuple[str, ...]:
    definition = get_cxr_finding_type_definition(finding_type)
    if definition is None:
        return (canonicalize_cxr_finding_type(finding_type).replace("_", " "),)
    return definition.concept_terms()


def cxr_evidence_terms_for_type(finding_type: str) -> tuple[str, ...]:
    canonical = canonicalize_cxr_finding_type(finding_type)
    terms = [
        *cxr_concept_terms_for_type(canonical),
        *CXR_EVIDENCE_SUPPORT_TERMS_BY_TYPE.get(canonical, ()),
    ]
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        key = " ".join(str(term).lower().replace("_", " ").split())
        if key and key not in seen:
            seen.add(key)
            deduped.append(term)
    return tuple(deduped)


def canonicalize_cxr_anatomy(anatomy: Any) -> str:
    normalized = _normalize_anatomy_text(anatomy)
    if not normalized:
        return "unknown"
    alias = CXR_ANATOMY_ALIASES.get(normalized)
    if alias:
        return alias
    tokens = set(normalized.split("_"))
    if "costophrenic" in tokens or ("cp" in tokens and "angle" in tokens):
        return "costophrenic_angle"
    lung_like = (
        "lung" in tokens or "lobe" in tokens or "lingula" in tokens
        or {"apical", "apex", "apices", "basilar", "basal", "base", "bases", "perihilar"} & tokens
    )
    if lung_like:
        # Preserve the lung zone (side is captured separately as laterality) so that
        # distinct lobes/zones are not collapsed into one identity key.
        if {"upper", "apical", "apex", "apices"} & tokens:
            return "upper_lung_zone"
        if {"mid", "middle"} & tokens:
            return "mid_lung_zone"
        if {"lower", "base", "bases", "basilar", "basal"} & tokens or "lingula" in tokens:
            return "lower_lung_zone"
        return "lung"
    if "hemidiaphragm" in tokens or "diaphragm" in tokens or "hemidiaphragms" in tokens:
        return "diaphragm"
    if "hilar" in tokens or "hilum" in tokens or "hila" in tokens:
        return "hilum"
    if "cardiac" in tokens or "heart" in tokens or "cardiomediastinal" in tokens:
        return "cardiac_silhouette"
    if "mediastinum" in tokens or "mediastinal" in tokens:
        return "mediastinum"
    if "aorta" in tokens or "aortic" in tokens:
        return "aorta"
    if "trachea" in tokens or "carina" in tokens or "tracheal" in tokens:
        return "trachea"
    if "clavicle" in tokens or "clavicular" in tokens:
        return "clavicle"
    if "spine" in tokens or "spinal" in tokens or "vertebral" in tokens or "vertebra" in tokens:
        return "spine"
    if "rib" in tokens or "ribs" in tokens:
        return "rib"
    if "pleura" in tokens or "pleural" in tokens:
        return "pleura"
    if "chest" in tokens and "wall" in tokens:
        return "chest_wall"
    if "shoulder" in tokens:
        return "shoulder"
    if "breast" in tokens or "nipple" in tokens:
        return "breast"
    if "neck" in tokens:
        return "neck"
    if "abdomen" in tokens or "subdiaphragmatic" in tokens:
        return "abdomen"
    return normalized


def all_cxr_finding_types() -> tuple[str, ...]:
    return tuple(CXR_TAXONOMY_BY_TYPE.keys())


def cxr_taxonomy_prompt_block() -> str:
    """Compact CXR taxonomy block for LLM prompts."""
    lines: list[str] = []
    for item in INITIAL_CXR_FINDING_TYPES:
        lines.append(f"- {item.finding_type}: {item.definition}")
        lines.append(f"  synonyms: {', '.join(item.synonyms)}")
        if item.exclusion_rules:
            lines.append(f"  exclusions: {' '.join(item.exclusion_rules)}")
    return "\n".join(lines)
