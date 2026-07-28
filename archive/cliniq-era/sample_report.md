# Sample Radiology Reports for Demo

Paste any of these into the radiology workflow at **Demo → Patient A → Add New Data → Radiology Report**.

---

## Report 1: CT Chest (Lung Nodule)

```
CT CHEST WITH CONTRAST

CLINICAL HISTORY: 65-year-old male with history of smoking, follow-up for pulmonary nodule.

TECHNIQUE: Helical CT of the chest was performed with intravenous contrast.

COMPARISON: Prior CT chest dated 2024-01-15.

FINDINGS:
Lungs and Airways: A 2.3 cm speculated nodule is noted in the left lower lobe, unchanged from prior examination. No new pulmonary nodules. Airways are patent.

Pleura: No pleural effusion. There is pleural thickening along the left lower costal pleural margin, stable.

Mediastinum and Hila: Granulomatous calcifications are seen in hilar lymph nodes. Heart size normal. No pericardial effusion.

Chest Wall and Soft Tissues: Periosteal regrowth does not fully bridge a surgical fracture of the right posterior sixth rib. No soft tissue masses.

Upper Abdomen: Limited views of the upper abdomen are unremarkable.

IMPRESSION:
1. Stable 2.3 cm left lower lobe speculated nodule, suspicious for primary lung malignancy.
2. Stable granulomatous calcifications in hilar nodes.
3. Incomplete healing of right posterior sixth rib surgical fracture.
4. No evidence of metastatic disease.
```

---

## Report 2: MRI Brain (Incidental Findings)

```
MRI BRAIN WITH AND WITHOUT CONTRAST

CLINICAL HISTORY: 48-year-old female with chronic headaches.

TECHNIQUE: Multiplanar multisequence MRI of the brain was performed before and after intravenous gadolinium administration.

COMPARISON: None.

FINDINGS:
Parenchyma: No evidence of mass effect, midline shift, or abnormal parenchymal enhancement. Gray-white matter differentiation is preserved. No hemorrhage or territorial infarct.

Ventricular System and Extra-axial Spaces: Ventricles are normal in size. Extra-axial spaces are normal. No hydrocephalus.

Vasculature: No evidence of abnormal vascular enhancement. Major intracranial vessels demonstrate normal flow voids.

Sella and Suprasellar Region: The suprasellar region is normal. The pituitary gland is unremarkable.

Posterior Fossa: A small approximately 1.5 cm CSF space is noted at the anterior aspect of the right cerebellum with slight indentation, consistent with a small incidental arachnoid cyst.

Paranasal Sinuses and Mastoids: There is pneumatization with fluid in the right petrous apex air cells. The nasopharyngeal soft tissues appear slightly prominent.

Craniocervical Junction: Appears normal.

IMPRESSION:
1. Small incidental arachnoid cyst at the anterior aspect of the right cerebellum.
2. Fluid in the right petrous apex air cells, likely inflammatory.
3. Slight prominence of nasopharyngeal soft tissues, correlate clinically.
4. Otherwise unremarkable MRI of the brain.
```

---

## Report 3: Knee X-Ray (Degenerative)

```
RADIOGRAPH LEFT KNEE (3 VIEWS)

CLINICAL HISTORY: 72-year-old female with left knee pain and stiffness.

TECHNIQUE: AP, lateral, and sunrise views of the left knee.

COMPARISON: None available.

FINDINGS:
Alignment: Mild lateral translocation of the tibia relative to the femur is noted.

Joint Spaces: Moderate joint space narrowing is present in the left medial compartment with associated osteophytes and small spurs. Mild degenerative changes are also seen in the left lateral compartment.

Bones: No acute fracture or dislocation. No foreign body. Bone mineralization is adequate.

Soft Tissues: No significant soft tissue swelling. No joint effusion.

IMPRESSION:
1. Moderate osteoarthritis of the bilateral medial compartments of the knees, left greater than right.
2. Mild lateral tibial translocation suggesting chronic ligamentous laxity.
3. No acute fracture or dislocation.
```

---

## Usage in the Demo

1. Go to the patient detail page (**Demo → Patient A**)
2. Click **"Radiology Report"** in the Workflows tab
3. Paste one of the reports above into the text area
4. Select the modality (CT, MRI, or X-Ray) and body region
5. Click **Process** — the system will extract clinical facts
6. Review each fact (approve/reject/edit)
7. Click **Submit Approved Facts** to ingest into the Fact Graph

The extracted facts include entity name, RadLex grounding, certainty score, body region, and evidence text from the source report.
