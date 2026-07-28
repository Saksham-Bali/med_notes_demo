"""
Rule-based finding extractor using spaCy NLP.

Extracts high-confidence findings from radiology reports using pattern
matching and NegEx-style negation detection. This serves as Tier 0 in the
hybrid extraction pipeline — findings extracted here skip the LLM entirely,
reducing cost and latency.

Targets:
- Measurements with dimensions (e.g. "3.2 x 2.1 cm mass")
- Named anatomical findings with clear modifiers
- Negated findings (e.g. "no pleural effusion")
- Standard comparison phrases (e.g. "stable", "unchanged", "increased")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Negation patterns (NegEx-inspired)
# ---------------------------------------------------------------------------
_NEGATION_PRE = re.compile(
    r"\b(?:no\s+evidence\s+of|no\s+acute|no\s+significant|no\s+definite|"
    r"negative\s+for|absence\s+of|without\s+evidence\s+of|without|"
    r"not\s+identified|not\s+seen|not\s+detected|no)\b",
    re.IGNORECASE,
)

_NEGATION_POST = re.compile(
    r"\b(?:is\s+absent|are\s+absent|not\s+seen|not\s+identified|"
    r"not\s+detected|is\s+negative|are\s+negative)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Measurement patterns
# ---------------------------------------------------------------------------
_MEASUREMENT_RE = re.compile(
    r"(?P<val1>\d+\.?\d*)\s*"
    r"(?:x\s*(?P<val2>\d+\.?\d*)\s*)??"
    r"(?:x\s*(?P<val3>\d+\.?\d*)\s*)??"
    r"(?P<unit>cm|mm|centimeters?|millimeters?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Change/comparison patterns
# ---------------------------------------------------------------------------
_CHANGE_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "stable",
        re.compile(r"\b(?:stable|unchanged|no\s+(?:significant\s+)?change)\b", re.I),
    ),
    (
        "increased",
        re.compile(
            r"\b(?:increas(?:ed|ing)|enlarg(?:ed|ing)|worsen(?:ed|ing)|progress(?:ed|ing)|grow(?:n|ing))\b",
            re.I,
        ),
    ),
    (
        "decreased",
        re.compile(
            r"\b(?:decreas(?:ed|ing)|smaller|improv(?:ed|ing)|resolv(?:ed|ing)|diminish(?:ed|ing)|regress(?:ed|ing))\b",
            re.I,
        ),
    ),
    ("new", re.compile(r"\bnew(?:ly)?\b", re.I)),
]

# ---------------------------------------------------------------------------
# Common finding patterns with entity types
# ---------------------------------------------------------------------------
_FINDING_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("pleural_effusion", re.compile(r"\bpleural\s+effusion\b", re.I)),
    ("pericardial_effusion", re.compile(r"\bpericardial\s+effusion\b", re.I)),
    ("pneumothorax", re.compile(r"\bpneumothorax\b", re.I)),
    ("atelectasis", re.compile(r"\batelectasis\b", re.I)),
    ("consolidation", re.compile(r"\bconsolidation\b", re.I)),
    (
        "pulmonary_edema",
        re.compile(r"\b(?:pulmonary\s+edema|pulmonary\s+congestion)\b", re.I),
    ),
    ("cardiomegaly", re.compile(r"\bcardiomegaly\b", re.I)),
    ("fracture", re.compile(r"\bfracture\b", re.I)),
    ("lymphadenopathy", re.compile(r"\blymphadenopathy\b", re.I)),
    ("mass", re.compile(r"\b(?:mass|masses)\b", re.I)),
    ("nodule", re.compile(r"\b(?:nodule|nodules|nodular)\b", re.I)),
    ("metastasis", re.compile(r"\b(?:metastas[ei]s|metastatic|mets?)\b", re.I)),
    ("calcification", re.compile(r"\bcalcification(?:s)?\b", re.I)),
    ("stenosis", re.compile(r"\bstenosis\b", re.I)),
    ("herniation", re.compile(r"\b(?:herniation|hernia)\b", re.I)),
    (
        "hemorrhage",
        re.compile(
            r"\b(?:hemorrhage|haemorrhage|bleeding|hematoma|microhemorrhage|microhemorrhages|microbleed|microbleeds)\b",
            re.I,
        ),
    ),
    ("infarction", re.compile(r"\b(?:infarct(?:ion)?|ischemi[ac])\b", re.I)),
    ("thrombosis", re.compile(r"\b(?:thrombosis|thrombus|thrombotic)\b", re.I)),
    ("aneurysm", re.compile(r"\baneurysm\b", re.I)),
    ("pneumonia", re.compile(r"\bpneumonia\b", re.I)),
    ("ascites", re.compile(r"\bascites\b", re.I)),
    ("hydrocephalus", re.compile(r"\bhydrocephalus\b", re.I)),
    ("edema", re.compile(r"\bedema\b", re.I)),
    ("effusion", re.compile(r"\beffusion\b", re.I)),
    ("opacity", re.compile(r"\b(?:opacity|opacities|opacification)\b", re.I)),
    ("hepatomegaly", re.compile(r"\bhepatom[ae]galy\b", re.I)),
    ("splenomegaly", re.compile(r"\bsplenomeg[ae]ly\b", re.I)),
    # Musculoskeletal
    (
        "joint_space_narrowing",
        re.compile(
            r"\b(?:joint\s+space\s+narrowing|narrowing\s+of\s+(?:the\s+)?(?:medial|lateral|tibiofemoral|patellofemoral|femorotibial)\s+compartment|compartment\s+narrowing)\b",
            re.I,
        ),
    ),
    (
        "osteophytes",
        re.compile(r"\b(?:osteophytes?|osteophytosis|spurs?|spurring)\b", re.I),
    ),
    (
        "degenerative_changes",
        re.compile(
            r"\bdegenerative\s+(?:changes?|disease|arthriti[cs]|joint\s+disease)\b",
            re.I,
        ),
    ),
    ("dislocation", re.compile(r"\bdislocation\b", re.I)),
    ("osteoarthritis", re.compile(r"\bosteoarthritis\b", re.I)),
    # Neurological
    (
        "midline_shift",
        re.compile(
            r"\b(?:midline\s+shift|shift\s+of\s+(?:normally\s+)?midline)\b", re.I
        ),
    ),
    (
        "enhancement",
        re.compile(
            r"\b(?:abnormal|parenchymal|vascular|meningeal|leptomeningeal|"
            r"subcortical|cortical|patchy|scattered|peripheral|nodular|ring|"
            r"linear|subtle)\s+enhanc(?:ement|ing)\b"
            r"|\benhanc(?:ement|ing)\s+(?:foci|focus|areas?|regions?|lesions?)\b",
            re.I,
        ),
    ),
    (
        "mass_effect",
        re.compile(r"\bmass\s+effect\b", re.I),
    ),
    (
        "mucosal_thickening",
        re.compile(
            r"\bmucosal\s+thickening\b"
            r"|\bmucosal\s+(?:disease|change|abnormalit(?:y|ies))\b",
            re.I,
        ),
    ),
    (
        "white_matter_changes",
        re.compile(
            r"\bwhite\s+matter\s+(?:signal|chang(?:e|es)|abnormalit(?:y|ies)|disease|lesion|hyperintensit(?:y|ies))\b",
            re.I,
        ),
    ),
    (
        "diffusion_restriction",
        re.compile(
            r"\b(?:diffusion\s+restriction|restricted\s+diffusion|slow(?:ed)?\s+diffusion|fast\s+diffusion)\b",
            re.I,
        ),
    ),
    (
        "flair_signal_abnormality",
        re.compile(
            r"\b(?:FLAIR|T2[\s\-/]*FLAIR)\s+(?:signal|hyperintens(?:e|ity)|abnormalit(?:y|ies)|hyperintense)\b"
            r"|\bFLAIR\s+subcortical\s+hyperintens(?:e|ity)\b",
            re.I,
        ),
    ),
    (
        "lymphoma",
        re.compile(
            r"\b(?:CNS\s+)?lymphoma\b",
            re.I,
        ),
    ),
    (
        "glioma",
        re.compile(
            r"\b(?:glioma|glioblastoma|gliomatous|GBM|high-grade\s+glioma|low-grade\s+glioma)\b",
            re.I,
        ),
    ),
    ("encephalitis", re.compile(r"\b(?:encephalitis|encephalopathy)\b", re.I)),
    (
        "small_vessel_disease",
        re.compile(
            r"\b(?:small\s+vessel\s+(?:ischemic\s+)?disease|chronic\s+small\s+vessel|microangiopath(?:y|ic))\b",
            re.I,
        ),
    ),
    (
        "subgaleal_collection",
        re.compile(
            r"\bsubgaleal\s+(?:fluid|hematoma|gas|collection|pneumocephalus)\b", re.I
        ),
    ),
    # Pleural
    ("pleural_thickening", re.compile(r"\bpleural\s+thickening\b", re.I)),
    # Oncologic pathology — only patterns the LLM consistently misses as named entities
    # NOTE: broad terms (carcinoma, lymphoma, embolism, dissection) are intentionally excluded
    # because the LLM already extracts them with full context (e.g. "invasive ductal carcinoma")
    # and rule-extracted generic names create FPs by failing soft-match against specific gold entries.
    ("glioblastoma", re.compile(r"\b(?:glioblastoma|GBM)\b", re.I)),
    ("sarcoidosis", re.compile(r"\bsarcoidosis\b", re.I)),
    # Vascular — only specific compound terms the LLM tends to miss
    ("pulmonary_embolism", re.compile(r"\bpulmonary\s+embolism\b", re.I)),
    ("aortic_dissection", re.compile(r"\baortic\s+dissection\b", re.I)),
    (
        "deep_vein_thrombosis",
        re.compile(r"\b(?:deep\s+(?:venous|vein)\s+thrombosis|DVT)\b", re.I),
    ),
    (
        "atherosclerosis",
        re.compile(
            r"\b(?:atherosclerosis|atherosclerotic\s+(?:disease|plaque|calcification))\b",
            re.I,
        ),
    ),
    # Lymph nodes (supplement lymphadenopathy — catches "enlarged lymph node" etc.)
    (
        "lymph_node",
        re.compile(
            r"\b(?:enlarged|prominent|pathologic(?:ally)?|hypermetabolic|suspicious|necrotic|reactive|matted)\s+(?:\w+\s+){0,2}lymph\s+nodes?\b",
            re.I,
        ),
    ),
    # GI — additional
    (
        "diverticulosis",
        re.compile(
            r"\b(?:diverticulosis|diverticulitis|diverticular\s+(?:disease|change))\b",
            re.I,
        ),
    ),
    (
        "gallstones",
        re.compile(
            r"\b(?:gallstones?|cholelithiasis|choledocholithiasis|biliary\s+calculi)\b",
            re.I,
        ),
    ),
    (
        "bowel_obstruction",
        re.compile(
            r"\b(?:bowel\s+obstruction|small\s+bowel\s+obstruction|large\s+bowel\s+obstruction|ileus)\b",
            re.I,
        ),
    ),
    (
        "pancreatitis",
        re.compile(
            r"\b(?:pancreatitis|pancreatic\s+(?:inflammation|ductal\s+dilation))\b",
            re.I,
        ),
    ),
    (
        "air_fluid_level",
        re.compile(r"\b(?:air[\s-]fluid\s+levels?|air-fluid\s+interface)\b", re.I),
    ),
    (
        "colitis",
        re.compile(r"\b(?:colitis|ischemic\s+colitis|infectious\s+colitis)\b", re.I),
    ),
    # Renal / Adrenal
    (
        "renal_cyst",
        re.compile(
            r"\b(?:renal\s+cysts?|kidney\s+cysts?|simple\s+cyst(?:s)?\s+in\s+(?:the\s+)?kidney)\b",
            re.I,
        ),
    ),
    (
        "adrenal_adenoma",
        re.compile(r"\badrenal\s+(?:adenoma|nodule|mass|lesion)\b", re.I),
    ),
    # MSK — additional
    (
        "tendinosis",
        re.compile(
            r"\b(?:tendinosis|tendinitis|tendinopathy|calcific\s+tendinosis)\b", re.I
        ),
    ),
    ("subluxation", re.compile(r"\bsubluxation\b", re.I)),
    (
        "ligamentous_injury",
        re.compile(
            r"\b(?:ligament(?:ous)?\s+(?:tear|injury|laxity|disruption|sprain)|torn\s+ligament)\b",
            re.I,
        ),
    ),
    ("stress_fracture", re.compile(r"\bstress\s+fracture\b", re.I)),
    (
        "bone_marrow_edema",
        re.compile(
            r"\bbone\s+marrow\s+(?:edema|signal\s+change|abnormalit(?:y|ies))\b", re.I
        ),
    ),
    # Sinus / ENT
    ("mucosal_thickening", re.compile(r"\bmucosal\s+thickening\b", re.I)),
    (
        "sinusitis",
        re.compile(r"\b(?:sinusitis|sinus\s+disease|sinus\s+opacification)\b", re.I),
    ),
    # Breast
    ("architectural_distortion", re.compile(r"\barchitectural\s+distortion\b", re.I)),
    # NOTE: birads_assessment intentionally excluded — rule extracts wrong category value
    # (e.g. BI-RADS 0 from incomplete study instead of BI-RADS 5); LLM handles correctly.
    (
        "breast_microcalcifications",
        re.compile(r"\b(?:breast\s+)?microcalcification(?:s)?\b", re.I),
    ),
    # Postoperative
    (
        "postoperative_changes",
        re.compile(
            r"\b(?:post(?:operative|surgical|[-\s]op)\s+changes?|postsurgical\s+changes?|surgical\s+site|craniotomy\s+changes?|burr\s+hole)\b",
            re.I,
        ),
    ),
    # ── Week 2 additions: Address FNs from gold eval + top RadGraph-XL patterns ──
    # Neuro — brain-specific (STRATEGIC_ANALYSIS gap: mass_effect, ventriculomegaly)
    ("mass_effect", re.compile(r"\bmass\s+effect\b", re.I)),
    (
        "ventriculomegaly",
        re.compile(
            r"\b(?:ventriculomegaly|ventricular\s+enlarg(?:ement)?|enlarged\s+ventricl)\b",
            re.I,
        ),
    ),
    (
        "sulcal_effacement",
        re.compile(
            r"\b(?:sulcal\s+effacement|effacement\s+of\s+(?:the\s+)?sulci|sulcal\s+narrowing)\b",
            re.I,
        ),
    ),
    (
        "cerebral_atrophy",
        re.compile(
            r"\b(?:cerebral\s+atrophy|cortical\s+atrophy|generalized\s+atrophy|brain\s+atrophy)\b",
            re.I,
        ),
    ),
    (
        "leukoaraiosis",
        re.compile(
            r"\b(?:leukoaraiosis|periventricular\s+white\s+matter\s+(?:changes|disease|hypodensit)|white\s+matter\s+hypodensit)\b",
            re.I,
        ),
    ),
    ("acute_infarct", re.compile(r"\bacute\s+(?:ischemic\s+)?infarct(?:ion)?\b", re.I)),
    (
        "chronic_infarct",
        re.compile(r"\bchronic\s+(?:ischemic\s+)?infarct(?:ion)?\b", re.I),
    ),
    (
        "subdural_hematoma",
        re.compile(r"\bsubdural\s+(?:hematoma|hemorrhage|collection|hygroma)\b", re.I),
    ),
    (
        "epidural_hematoma",
        re.compile(r"\bepidural\s+(?:hematoma|hemorrhage|collection)\b", re.I),
    ),
    (
        "subarachnoid_hemorrhage",
        re.compile(r"\bsubarachnoid\s+(?:hemorrhage|blood|hematoma|SAH)\b", re.I),
    ),
    (
        "intraparenchymal_hemorrhage",
        re.compile(r"\bintraparenchymal\s+(?:hemorrhage|hematoma|bleed)\b", re.I),
    ),
    ("cerebral_edema", re.compile(r"\b(?:cerebral|brain)\s+edema\b", re.I)),
    (
        "brain_metastasis",
        re.compile(r"\bbrain\s+met(?:astasi[sz]|s)?\b|\bcerebral\s+metastasi\b", re.I),
    ),
    ("meningioma", re.compile(r"\bmeningioma\b", re.I)),
    ("flow_voids", re.compile(r"\bflow\s+voids?\b", re.I)),
    ("restricted_diffusion", re.compile(r"\brestricted\s+diffusion\b", re.I)),
    # Oncologic — gold FNs: pulmonary mets, hepatic mets, osteitis
    (
        "pulmonary_metastases",
        re.compile(
            r"\b(?:pulmonary\s+metastas[ei]s|lung\s+metastas[ei]s|pulmonary\s+mets?|lung\s+mets?)\b",
            re.I,
        ),
    ),
    (
        "hepatic_metastases",
        re.compile(
            r"\b(?:hepatic\s+metastas[ei]s|liver\s+metastas[ei]s|hepatic\s+mets?|liver\s+mets?)\b",
            re.I,
        ),
    ),
    (
        "osseous_metastases",
        re.compile(
            r"\b(?:osseous\s+metastas[ei]s|bone\s+metastas[ei]s|skeletal\s+metastas[ei]s|bone\s+mets?)\b",
            re.I,
        ),
    ),
    (
        "lymph_node_metastasis",
        re.compile(
            r"\b(?:nodal\s+metastas[ei]s|lymph\s+node\s+metastas[ei]s|metastatic\s+lymph\s+node)\b",
            re.I,
        ),
    ),
    (
        "osteitis_condensans_ilii",
        re.compile(r"\bosteitis\s+condensans\b|\bpelvic\s+osteitis\b", re.I),
    ),
    (
        "peritoneal_metastases",
        re.compile(
            r"\b(?:peritoneal\s+(?:metastas[ei]s|implants?|carcinomatosis)|omental\s+(?:metastas[ei]s|caking))\b",
            re.I,
        ),
    ),
    (
        "malignant_pleural_effusion",
        re.compile(r"\bmalignant\s+pleural\s+effusion\b", re.I),
    ),
    (
        "tumor_recurrence",
        re.compile(
            r"\b(?:tumor\s+recurrence|recurrent\s+(?:tumor|mass|disease|malignancy)|local\s+recurrence)\b",
            re.I,
        ),
    ),
    # Pulmonary — RadGraph-XL top patterns + gold FNs
    ("pneumothorax_small", re.compile(r"\bsmall\s+pneumothorax\b", re.I)),
    ("dependent_atelectasis", re.compile(r"\bdependent\s+atelectasis\b", re.I)),
    (
        "subsegmental_atelectasis",
        re.compile(
            r"\b(?:subsegmental|bibasilar|basilar|linear)\s+atelectasis\b", re.I
        ),
    ),
    (
        "ground_glass_opacity",
        re.compile(r"\b(?:ground[\s-]glass\s+opacit(?:y|ies)|GGO)\b", re.I),
    ),
    (
        "interstitial_thickening",
        re.compile(
            r"\b(?:interstitial\s+thickening|interstitial\s+markings\s+increased|peribronchial\s+thickening)\b",
            re.I,
        ),
    ),
    (
        "emphysema",
        re.compile(
            r"\b(?:emphysema|emphysematous\s+change|hyperinflation|hyperaeration)\b",
            re.I,
        ),
    ),
    ("bronchiectasis", re.compile(r"\bbronchiectasis\b", re.I)),
    (
        "cavity",
        re.compile(
            r"\b(?:pulmonary\s+cavit(?:y|ies)|cavitary\s+(?:lesion|mass))\b", re.I
        ),
    ),
    (
        "pulmonary_fibrosis",
        re.compile(
            r"\b(?:pulmonary\s+fibrosis|fibrotic\s+change|interstitial\s+fibrosis|pulmonary\s+scars?)\b",
            re.I,
        ),
    ),
    ("nodular_opacities", re.compile(r"\bnodular\s+opacit(?:y|ies)\b", re.I)),
    (
        "focal_pulmonary_abnormality",
        re.compile(
            r"\bfocal\s+pulmonary\s+(?:abnormalit(?:y|ies)|opacity|lesion)\b", re.I
        ),
    ),
    (
        "hilar_adenopathy",
        re.compile(r"\bhilar\s+(?:adenopathy|lymphadenopathy|lymph\s+nodes?)\b", re.I),
    ),
    (
        "mediastinal_adenopathy",
        re.compile(
            r"\bmediastinal\s+(?:adenopathy|lymphadenopathy|lymph\s+nodes?)\b", re.I
        ),
    ),
    (
        "airspace_disease",
        re.compile(
            r"\b(?:airspace\s+disease|airspace\s+opacity|alveolar\s+opacit(?:y|ies))\b",
            re.I,
        ),
    ),
    (
        "pleural_plaques",
        re.compile(r"\bpleural\s+(?:plaques?|calcification|scarring|fibrosis)\b", re.I),
    ),
    # Abdominal / GI — RadGraph-XL top (free fluid 119x, free air 77x, fat stranding 15x)
    (
        "free_fluid",
        re.compile(
            r"\bfree\s+fluid\b|\bfree\s+(?:abdominal|pelvic|peritoneal)\s+fluid\b", re.I
        ),
    ),
    (
        "free_air",
        re.compile(r"\bfree\s+air\b|\bpneumoperitoneum\b|\bextraluminal\s+air\b", re.I),
    ),
    (
        "fat_stranding",
        re.compile(
            r"\bfat\s+stranding\b|\bpericolic\s+fat\s+stranding\b|\bmesenteric\s+fat\s+stranding\b",
            re.I,
        ),
    ),
    (
        "fluid_collection",
        re.compile(
            r"\b(?:fluid\s+collection|fluid-filled\s+collection|abscess|pelvic\s+collection)\b",
            re.I,
        ),
    ),
    (
        "liver_lesion",
        re.compile(
            r"\b(?:hepatic\s+lesion|liver\s+lesion|hepatic\s+mass|liver\s+mass|hepatic\s+nodule)\b",
            re.I,
        ),
    ),
    (
        "liver_cirrhosis",
        re.compile(
            r"\b(?:cirrhosis|cirrhotic\s+liver|hepatic\s+cirrhosis|liver\s+cirrhosis)\b",
            re.I,
        ),
    ),
    (
        "bile_duct_dilation",
        re.compile(
            r"\b(?:biliary\s+dilation|common\s+bile\s+duct\s+dilation|CBD\s+dilation|biliary\s+obstruction)\b",
            re.I,
        ),
    ),
    (
        "cholecystitis",
        re.compile(
            r"\b(?:cholecystitis|gallbladder\s+wall\s+thickening|pericholecystic)\b",
            re.I,
        ),
    ),
    (
        "appendicitis",
        re.compile(
            r"\b(?:appendicitis|periappendiceal|appendiceal\s+(?:wall\s+thickening|inflammation))\b",
            re.I,
        ),
    ),
    (
        "bowel_wall_thickening",
        re.compile(
            r"\bbowel\s+wall\s+thickening\b|\bcolonic\s+wall\s+thickening\b|\bsmall\s+bowel\s+wall\s+thickening\b",
            re.I,
        ),
    ),
    (
        "mesenteric_lymphadenopathy",
        re.compile(r"\bmesenteric\s+(?:lymphadenopathy|lymph\s+nodes?)\b", re.I),
    ),
    (
        "perforation",
        re.compile(
            r"\b(?:bowel\s+perforation|visceral\s+perforation|hollow\s+viscus\s+perforation|gastric\s+perforation)\b",
            re.I,
        ),
    ),
    (
        "gastrointestinal_bleeding",
        re.compile(
            r"\b(?:GI\s+bleeding|gastrointestinal\s+bleed(?:ing)?|rectal\s+bleed(?:ing)?|melena)\b",
            re.I,
        ),
    ),
    (
        "portal_hypertension",
        re.compile(r"\b(?:portal\s+hypertension|portal\s+HTN)\b", re.I),
    ),
    (
        "splenomegaly_portal",
        re.compile(r"\bsplenomegaly\b", re.I),
    ),  # supplement existing
    (
        "pancreatic_mass",
        re.compile(
            r"\b(?:pancreatic\s+(?:mass|tumor|carcinoma|adenocarcinoma)|pancreatic\s+head\s+mass)\b",
            re.I,
        ),
    ),
    # Renal / Adrenal — RadGraph-XL + gold FN renal_cyst
    (
        "renal_mass",
        re.compile(
            r"\b(?:renal\s+(?:mass|tumor|carcinoma|cell\s+carcinoma|lesion)|kidney\s+(?:mass|tumor))\b",
            re.I,
        ),
    ),
    (
        "hydronephrosis",
        re.compile(
            r"\b(?:hydronephrosis|hydroureter|ureteral\s+obstruction|renal\s+pelvis\s+dilation)\b",
            re.I,
        ),
    ),
    (
        "nephrolithiasis",
        re.compile(
            r"\b(?:nephrolithiasis|kidney\s+stone|renal\s+calculi|urolithiasis|ureterolithiasis)\b",
            re.I,
        ),
    ),
    (
        "renal_infarct",
        re.compile(r"\b(?:renal\s+infarct(?:ion)?|renal\s+ischemia)\b", re.I),
    ),
    # Vascular — supplement existing
    (
        "aortic_aneurysm",
        re.compile(
            r"\b(?:aortic\s+aneurysm|abdominal\s+aortic\s+aneurysm|AAA|thoracic\s+aortic\s+aneurysm)\b",
            re.I,
        ),
    ),
    (
        "aortic_stenosis",
        re.compile(
            r"\b(?:aortic\s+stenosis|aortic\s+valve\s+stenosis|calcific\s+aortic\s+stenosis)\b",
            re.I,
        ),
    ),
    (
        "mesenteric_ischemia",
        re.compile(
            r"\b(?:mesenteric\s+ischemia|bowel\s+ischemia|intestinal\s+ischemia)\b",
            re.I,
        ),
    ),
    (
        "venous_thromboembolism",
        re.compile(r"\b(?:venous\s+thromboembolism|VTE|IVC\s+thrombus)\b", re.I),
    ),
    (
        "carotid_stenosis",
        re.compile(
            r"\b(?:carotid\s+stenosis|internal\s+carotid\s+stenosis|carotid\s+occlusion)\b",
            re.I,
        ),
    ),
    # Cardiac
    (
        "wall_motion_abnormality",
        re.compile(
            r"\b(?:wall\s+motion\s+abnormalit(?:y|ies)|hypokinesis|akinesis|dyskinesis)\b",
            re.I,
        ),
    ),
    (
        "myocardial_infarction",
        re.compile(r"\b(?:myocardial\s+infarction|MI\b|NSTEMI|STEMI)\b", re.I),
    ),
    (
        "cardiac_tamponade",
        re.compile(
            r"\b(?:cardiac\s+tamponade|tamponade|pericardial\s+tamponade)\b", re.I
        ),
    ),
    (
        "congestive_heart_failure",
        re.compile(
            r"\b(?:congestive\s+heart\s+failure|CHF|decompensated\s+heart\s+failure|fluid\s+overload)\b",
            re.I,
        ),
    ),
    (
        "coronary_artery_disease",
        re.compile(
            r"\b(?:coronary\s+artery\s+disease|CAD|coronary\s+atherosclerosis)\b", re.I
        ),
    ),
    # MSK — supplement existing
    (
        "tibial_translocation",
        re.compile(
            r"\b(?:tibial\s+(?:lateral\s+)?translocation|lateral\s+translocation\s+of\s+the\s+tibia)\b",
            re.I,
        ),
    ),
    (
        "avascular_necrosis",
        re.compile(
            r"\b(?:avascular\s+necrosis|AVN|osteonecrosis|aseptic\s+necrosis)\b", re.I
        ),
    ),
    (
        "sacroiliitis",
        re.compile(
            r"\b(?:sacroiliitis|sacroiliac\s+joint\s+(?:inflammation|disease|erosion))\b",
            re.I,
        ),
    ),
    (
        "compression_fracture",
        re.compile(
            r"\b(?:compression\s+fracture|vertebral\s+compression\s+fracture|vertebral\s+collapse)\b",
            re.I,
        ),
    ),
    (
        "spondylosis",
        re.compile(r"\b(?:spondylosis|spondylolysis|spondylolisthesis)\b", re.I),
    ),
    (
        "disc_herniation",
        re.compile(
            r"\b(?:disc\s+(?:herniation|protrusion|extrusion|bulge)|herniated\s+disc|disc\s+prolapse)\b",
            re.I,
        ),
    ),
    (
        "spinal_stenosis",
        re.compile(
            r"\b(?:spinal\s+(?:canal\s+)?stenosis|central\s+canal\s+stenosis|neural\s+foraminal\s+stenosis)\b",
            re.I,
        ),
    ),
    (
        "osteomyelitis",
        re.compile(
            r"\b(?:osteomyelitis|bone\s+infection|vertebral\s+osteomyelitis|discitis)\b",
            re.I,
        ),
    ),
    (
        "pathologic_fracture",
        re.compile(
            r"\b(?:pathologic(?:al)?\s+fracture|insufficiency\s+fracture)\b", re.I
        ),
    ),
    # Soft tissue / abdomen wall
    (
        "hematoma",
        re.compile(r"\b(?:hematoma|haematoma|blood\s+collection)\b", re.I),
    ),  # supplement hemorrhage
    ("abscess", re.compile(r"\b(?:abscess|phlegmon|pyogenic\s+collection)\b", re.I)),
    ("lymphocele", re.compile(r"\b(?:lymphocele|lymph(?:atic)?\s+cyst)\b", re.I)),
    ("seroma", re.compile(r"\bseroma\b", re.I)),
    (
        "hiatal_hernia",
        re.compile(
            r"\b(?:hiatal\s+hernia|hiatus\s+hernia|sliding\s+hiatal\s+hernia)\b", re.I
        ),
    ),
    (
        "inguinal_hernia",
        re.compile(r"\b(?:inguinal\s+hernia|femoral\s+hernia)\b", re.I),
    ),
    # Lines / tubes / devices (high-frequency in RadGraph-XL, often FPs if extracted; keep specific)
    (
        "endotracheal_tube",
        re.compile(r"\b(?:endotracheal\s+tube|ETT|ET\s+tube)\b", re.I),
    ),
    ("nasogastric_tube", re.compile(r"\b(?:nasogastric\s+tube|NG\s+tube|NGT)\b", re.I)),
    (
        "central_venous_catheter",
        re.compile(
            r"\b(?:central\s+venous\s+(?:catheter|line)|PICC\s+line|Port-a-Cath|CVC)\b",
            re.I,
        ),
    ),
    (
        "drainage_catheter",
        re.compile(
            r"\b(?:drainage\s+(?:catheter|tube)|pigtail\s+(?:catheter|drain)|Jackson-Pratt|JP\s+drain)\b",
            re.I,
        ),
    ),
    (
        "surgical_clips",
        re.compile(
            r"\b(?:surgical\s+clips?|hemostatic\s+clips?|vascular\s+clips?)\b", re.I
        ),
    ),
    # Interval change / comparison anchors — helps LLM's longitudinal comparison
    (
        "interval_change",
        re.compile(
            r"\b(?:interval\s+(?:change|decrease|increase|development|resolution|improvement|worsening)|no\s+interval\s+change)\b",
            re.I,
        ),
    ),
    (
        "new_finding",
        re.compile(
            r"\bnew(?:ly)?\s+(?:developed|identified|seen|appearing|noted|demonstrated)\b",
            re.I,
        ),
    ),
    (
        "resolved_finding",
        re.compile(
            r"\b(?:resolved|resolving|no\s+longer\s+(?:seen|identified|visualized|present))\b",
            re.I,
        ),
    ),
]

# Certainty qualifiers
_CERTAINTY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("definite", re.compile(r"\b(?:definite(?:ly)?|confirmed|proven)\b", re.I)),
    ("probable", re.compile(r"\b(?:probable|probably|likely|suggestive)\b", re.I)),
    (
        "possible",
        re.compile(
            r"\b(?:possible|possibly|may\s+represent|cannot\s+exclude|questionable)\b",
            re.I,
        ),
    ),
    (
        "indeterminate",
        re.compile(r"\b(?:indeterminate|equivocal|uncertain|unclear)\b", re.I),
    ),
]


@dataclass
class RuleFinding:
    """A finding extracted by the rule-based system."""

    entity_name: str
    finding_type: str
    is_negated: bool
    certainty: str
    change_status: str | None
    measurement: dict[str, Any] | None
    span_start: int
    span_end: int
    sentence: str
    confidence: float  # rule-system confidence (not clinical certainty)


@dataclass
class RuleExtractionResult:
    """Result of rule-based extraction."""

    findings: list[RuleFinding] = field(default_factory=list)
    coverage_ratio: float = 0.0  # fraction of sentences that yielded findings


class RuleExtractor:
    """Extract findings from radiology reports using pattern matching.

    This is intentionally conservative — it only extracts findings where
    the pattern match is unambiguous. Anything uncertain is left for the
    LLM extractor.
    """

    def __init__(self):
        # Pre-compile sentence splitter
        self._sent_split = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|(?<=\n)\s*(?=\S)")

    def _split_sentences(self, text: str) -> list[tuple[str, int, int]]:
        """Split text into sentences with character offsets."""
        sentences = []
        parts = self._sent_split.split(text)
        offset = 0
        for part in parts:
            part = part.strip()
            if not part:
                continue
            start = text.find(part, offset)
            if start == -1:
                start = offset
            end = start + len(part)
            sentences.append((part, start, end))
            offset = end
        return sentences

    def _detect_negation(self, sentence: str, finding_start: int) -> bool:
        """Detect if a finding at a given position is negated."""
        # Check pre-negation in the 50 chars before the finding
        prefix = sentence[max(0, finding_start - 50) : finding_start]
        if _NEGATION_PRE.search(prefix):
            return True

        # Check post-negation in the 30 chars after the finding
        suffix = sentence[finding_start : finding_start + 80]
        if _NEGATION_POST.search(suffix):
            return True

        return False

    def _extract_measurement(self, context: str) -> dict[str, Any] | None:
        """Extract measurement from text near a finding."""
        match = _MEASUREMENT_RE.search(context)
        if not match:
            return None

        unit = match.group("unit").lower()
        if unit.startswith("centimeter"):
            unit = "cm"
        elif unit.startswith("millimeter"):
            unit = "mm"

        val1 = float(match.group("val1"))
        val2 = float(match.group("val2")) if match.group("val2") else None
        val3 = float(match.group("val3")) if match.group("val3") else None

        # Normalize to mm
        multiplier = 10.0 if unit == "cm" else 1.0
        normalized_mm = val1 * multiplier

        result: dict[str, Any] = {
            "value": val1,
            "unit": unit,
            "normalized_mm": normalized_mm,
        }
        if val2 is not None:
            result["value2"] = val2
        if val3 is not None:
            result["value3"] = val3
        return result

    def _detect_change(self, sentence: str) -> str | None:
        """Detect change/comparison status."""
        for status, pattern in _CHANGE_PATTERNS:
            if pattern.search(sentence):
                return status
        return None

    def _detect_certainty(self, sentence: str) -> str:
        """Detect certainty qualifier."""
        for level, pattern in _CERTAINTY_PATTERNS:
            if pattern.search(sentence):
                return level
        return "definite"

    def extract(self, report_text: str) -> RuleExtractionResult:
        """Extract findings from report text using rules.

        Returns findings with high confidence. Sentences that don't match
        any pattern are left for the LLM extractor.
        """
        if not report_text or not report_text.strip():
            return RuleExtractionResult()

        # Collapse mid-sentence newlines into spaces so that multi-line
        # phrases like "shift of normally\nmidline structures" stay intact
        # for both sentence splitting and pattern matching.
        report_text = re.sub(r"(?<![.!?])\n(?!\s*\n)", " ", report_text)

        sentences = self._split_sentences(report_text)
        findings: list[RuleFinding] = []
        sentences_with_findings = 0

        for sentence, sent_start, sent_end in sentences:
            sentence_findings: list[RuleFinding] = []

            for finding_type, pattern in _FINDING_PATTERNS:
                for match in pattern.finditer(sentence):
                    match_start = match.start()
                    match_end = match.end()

                    # Get context window for measurement/modifier extraction
                    ctx_start = max(0, match_start - 60)
                    ctx_end = min(len(sentence), match_end + 60)
                    context = sentence[ctx_start:ctx_end]

                    is_negated = self._detect_negation(sentence, match_start)
                    measurement = self._extract_measurement(context)
                    change_status = self._detect_change(sentence)
                    certainty = self._detect_certainty(sentence)

                    # Confidence based on pattern specificity
                    confidence = 0.85
                    if measurement:
                        confidence = 0.92
                    if is_negated:
                        confidence = 0.90  # negation patterns are reliable

                    # Use finding_type as entity name (clean label)
                    # rather than raw matched text for consistency
                    finding = RuleFinding(
                        entity_name=finding_type,
                        finding_type=finding_type,
                        is_negated=is_negated,
                        certainty=certainty,
                        change_status=change_status,
                        measurement=measurement,
                        span_start=sent_start + match_start,
                        span_end=sent_start + match_end,
                        sentence=sentence,
                        confidence=confidence,
                    )
                    sentence_findings.append(finding)

            # Deduplicate: if a longer match fully contains a shorter one,
            # keep only the longer (more specific) match.
            deduplicated: list[RuleFinding] = []
            sentence_findings.sort(
                key=lambda f: f.span_end - f.span_start, reverse=True
            )
            for f in sentence_findings:
                is_subspan = any(
                    d.span_start <= f.span_start
                    and d.span_end >= f.span_end
                    and (d.span_end - d.span_start) > (f.span_end - f.span_start)
                    for d in deduplicated
                )
                if not is_subspan:
                    deduplicated.append(f)

            if deduplicated:
                findings.extend(deduplicated)
                sentences_with_findings += 1

        coverage = sentences_with_findings / max(len(sentences), 1)
        return RuleExtractionResult(findings=findings, coverage_ratio=coverage)

    def to_extraction_format(
        self,
        result: RuleExtractionResult,
        chart_date: str,
        study_type: str = "Unknown",
    ) -> dict[str, Any]:
        """Convert rule findings to the same format as FindingExtractor output.

        This allows seamless integration with the downstream pipeline.
        """
        primary_findings = []
        significant_negatives = []

        for finding in result.findings:
            entry = {
                "entity_name": finding.entity_name,
                "finding_type": finding.finding_type,
                "is_negated": finding.is_negated,
                "certainty": finding.certainty,
                "change_status": finding.change_status or "not_compared",
                "measurement": finding.measurement,
                "span_start": finding.span_start,
                "span_end": finding.span_end,
                "extraction_method": "rule_based",
                "modality": study_type,
            }
            if finding.measurement:
                entry["measurement_normalized"] = finding.measurement.get(
                    "normalized_mm"
                )

            if finding.is_negated:
                significant_negatives.append(entry)
            else:
                primary_findings.append(entry)

        return {
            "report_metadata": {
                "study_date": chart_date,
                "study_type": study_type,
            },
            "primary_findings": primary_findings,
            "significant_negatives": significant_negatives,
            "overall_extraction_confidence": (
                sum(f.confidence for f in result.findings)
                / max(len(result.findings), 1)
            ),
            "critical_ambiguities": [],
        }
