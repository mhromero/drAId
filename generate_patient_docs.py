#!/usr/bin/env python3
"""
Generates fictional medical documents (TXT and PDF) for each FHIR patient.
All content is in English so the en_core_sci_md spaCy model produces valid embeddings.
Output: medical_search/data/{cip}/

Usage:
    python generate_patient_docs.py
"""

from pathlib import Path
import fitz  # PyMuPDF

ROOT = Path(__file__).parent
OUTPUT_BASE = ROOT / "medical_search" / "data"


def write_txt(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  TXT  {path.relative_to(ROOT)}")


def write_pdf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(45, 45, 550, 810)
    rc = page.insert_textbox(rect, content, fontsize=9.5, fontname="helv", align=0)
    if rc < 0:
        remaining = content[abs(rc):]
        page2 = doc.new_page(width=595, height=842)
        page2.insert_textbox(rect, remaining, fontsize=9.5, fontname="helv", align=0)
    doc.save(str(path))
    doc.close()
    print(f"  PDF  {path.relative_to(ROOT)}")


DOCS = {

    # ── 2800001234 · Carlos Martinez Lopez, 59 y/o male ─────────────────────
    "2800001234": {

        "nota_urgencias_2026-01-22.txt": """\
EMERGENCY DEPARTMENT REPORT
University Hospital La Paz — SERMAS
Date and time of visit: 22/01/2026  10:00
Patient: Martinez Lopez, Carlos
Date of birth: 14/03/1966  |  Sex: Male  |  CIP: 2800001234

CHIEF COMPLAINT
Sudden onset oppressive chest pain approximately 2 hours ago, radiating to the
jaw and left arm, associated with cold sweating. Patient reports similar but
milder episodes previously occurring during exertion.

RELEVANT MEDICAL HISTORY
- Arterial hypertension (since 2015), treated with Losartan 50 mg/day.
- Type 2 diabetes mellitus (since 2018), on Metformin 850 mg twice daily.
- Known ischemic heart disease (since 2021).
- Percutaneous coronary angioplasty with stent in proximal LAD (2023).
- Lipid-lowering therapy: Atorvastatin 40 mg at night.
- No known drug allergies.

PHYSICAL EXAMINATION
- BP: 152/90 mmHg  |  HR: 88 bpm  |  SpO2: 97%  |  Temp: 36.4 C
- Alert and oriented. Mild pallor.
- Cardiopulmonary auscultation: regular rhythm, no murmurs. Clear lung fields.
- Abdomen: soft, non-tender. Lower limbs: no oedema.

DIAGNOSTIC WORKUP
- 12-lead ECG: sinus rhythm at 88 bpm. No acute repolarisation changes. No blocks.
- Chest X-ray: normal cardiothoracic ratio. No infiltrates or pleural effusion.
- Urgent labs: Haemoglobin 13.1 g/dL. WBC 7.8 x10^9/L. Glucose 148 mg/dL.
  High-sensitivity Troponin I: 14 ng/L (normal <34 ng/L). Creatinine 0.95 mg/dL.

CLINICAL ASSESSMENT
Non-ST-elevation acute coronary syndrome (NSTEMI) low risk.
Decompensated stable angina. Unstable angina to be ruled out.

TREATMENT IN EMERGENCY DEPARTMENT
- Aspirin 300 mg orally as loading dose.
- Sublingual nitroglycerin 0.4 mg with partial clinical improvement.
- Continuous monitoring. Peripheral venous access.
- Observation 6 hours with serial Troponin at 3 h: 12 ng/L (decreasing).

DISCHARGE PLAN
Discharge home with urgent Cardiology follow-up within 48-72 hours.
Continue usual medication. Relative rest. Rescue sublingual nitroglycerin.
Warning signs: attend emergency if chest pain recurs.

Attending physician: Dr. Javier Ramos Ortiz
Medical licence: 28-12345
""",

        "informe_alta_urgencias_2026-01-23.txt": """\
CLINICAL DISCHARGE REPORT — EMERGENCY DEPARTMENT
University Hospital La Paz — SERMAS
Date of discharge: 23/01/2026  08:30
Patient: Martinez Lopez, Carlos  |  CIP: 2800001234  |  Age: 59

DIAGNOSIS AT DISCHARGE
- Decompensated stable angina. Acute coronary syndrome with necrosis ruled out.
- Poorly controlled arterial hypertension (peak BP 158/94 during observation).
- Type 2 diabetes mellitus.

CLINICAL SUMMARY
Patient admitted to emergency observation on 22/01/2026 for oppressive chest pain.
Serial troponins showed no criteria for myocardial necrosis. ECG without acute
ischaemic changes. Chest X-ray without acute findings. Patient remained 22 hours
under continuous monitoring. Favourable evolution with no new pain episodes.

DISCHARGE MEDICATION
1. Losartan 50 mg — 1 tablet in the morning.
2. Metformin 850 mg — 1 tablet with breakfast and dinner.
3. Atorvastatin 40 mg — 1 tablet at night.
4. Aspirin 100 mg — 1 tablet in the morning (added during this admission).
5. Sublingual nitroglycerin 0.4 mg — rescue if chest pain occurs.

RECOMMENDATIONS
- Low-salt, low saturated-fat diet.
- Strict glycaemic control. Do not stop Metformin.
- Avoid intense physical exertion until Cardiology review.
- Preferential appointment at Cardiology outpatient clinic (scheduled 10/03/2026).
- Return to emergency if: chest pain at rest >15 min, sudden dyspnoea,
  loss of consciousness or poorly tolerated palpitations.

Discharging physician: Dr. Javier Ramos Ortiz
""",

        "resultado_ecg_2026-01-22.txt": """\
ELECTROCARDIOGRAM REPORT
University Hospital La Paz — Cardiology Section
Date: 22/01/2026  10:10
Patient: Martinez Lopez, Carlos  |  CIP: 2800001234

PARAMETERS
- Rhythm: Regular sinus rhythm.
- Heart rate: 88 bpm.
- PR interval: 162 ms (normal).
- QRS duration: 88 ms (normal, no block).
- QTc: 420 ms (normal).
- Electrical axis: +45 degrees (normal).

FINDINGS
No acute repolarisation changes observed. No ST-segment elevation.
No pathological Q waves indicating prior necrosis in any lead.
T-wave morphology without significant alterations.
Compared with previous ECG from 2023: no relevant changes.

CONCLUSION
ECG within normal limits. No electrocardiographic criteria for acute coronary
syndrome at the time of recording.

Dr. Alejandro Vega Montero — On-call Cardiologist
""",

        "resultado_laboratorio_2026-03-10.txt": """\
LABORATORY REPORT — CONTROL BLOOD TEST
University Hospital La Paz — Clinical Analysis Department
Drawn: 10/03/2026  08:00  |  Report: 10/03/2026  11:00
Patient: Martinez Lopez, Carlos  |  CIP: 2800001234  |  Requesting physician: Dr. Mora

FULL BLOOD COUNT
Haemoglobin: 13.1 g/dL  [RR: 13.5-17.5]  LOW (mild)
Haematocrit: 39.8%  [RR: 41-53]  LOW (mild)
MCV: 88 fL (normal)
WBC: 7.8 x10^9/L (normal)  |  Neutrophils: 62%
Platelets: 198 x10^9/L (normal)

BIOCHEMISTRY
Fasting glucose: 142 mg/dL  [RR: 70-100]  HIGH (poor glycaemic control)
HbA1c: 7.4%  [target <7.0%]  HIGH
Creatinine: 0.95 mg/dL  |  eGFR: 76 mL/min/1.73m2  (G2 mild)
Total cholesterol: 168 mg/dL  (controlled with statin)
LDL: 92 mg/dL  [target <70 in high CV risk]  HIGH
HDL: 38 mg/dL  LOW
Triglycerides: 189 mg/dL  HIGH (mild)
Sodium: 139 mEq/L  |  Potassium: 4.1 mEq/L  |  Chloride: 103 mEq/L
ALT: 28 U/L  |  AST: 24 U/L  (normal on statin therapy)

OBSERVATIONS
Mild normocytic anaemia. Rule out iron deficiency at next control.
LDL above target in very high cardiovascular risk patient.
Consider statin dose adjustment or adding ezetimibe.
Suboptimal glycaemic control: review diet and Metformin adherence.
""",

        "nota_evolucion_cardiologia_2026-03-10.txt": """\
CARDIOLOGY OUTPATIENT FOLLOW-UP NOTE
University Hospital La Paz — SERMAS
Date: 10/03/2026  12:00
Patient: Martinez Lopez, Carlos  |  CIP: 2800001234
Physician: Dr. Isabel Mora Castellano — Cardiologist

REASON FOR VISIT
Review following unstable angina episode in January 2026. Follow-up of ischemic
heart disease with LAD stent.

HISTORY
Patient reports good exercise tolerance since January episode. No new episodes
of chest pain at rest or on exertion. Compliant with medication. Reports
occasional morning dizziness possibly related to morning hypotension.

PHYSICAL EXAMINATION
BP: 136/82 mmHg  |  HR: 74 bpm  |  SpO2: 98%
Auscultation: regular rhythm, no audible murmurs. Preserved vesicular murmur.
No ankle oedema.

RESULTS REVIEW
- Blood test (10/03/2026): Haemoglobin 13.1 (mild anaemia). LDL 92 mg/dL.
  HbA1c 7.4%. LDL above target (<70 mg/dL).
- ECG: Sinus rhythm, unchanged from previous.
- Echocardiogram (pending request): LVEF without recent data.

CLINICAL ASSESSMENT
- Stable ischemic heart disease. LAD stent patent (favourable clinical course).
- Arterial hypertension with suboptimal morning control.
- Dyslipidaemia: LDL above target in very high cardiovascular risk patient.
- Mild anaemia: to be investigated.

PLAN
1. Add Ezetimibe 10 mg at night to reach LDL target <70 mg/dL.
2. Request transthoracic echocardiogram.
3. Refer to haematology for anaemia workup.
4. Review Losartan dosing schedule (take at night to avoid morning hypotension).
5. Next review in 3 months with echocardiogram and blood test.

Dr. Isabel Mora Castellano  |  Medical licence: 28-67890
""",

        "informe_radiologia_2026-01-22.txt": """\
RADIOLOGY REPORT — CHEST X-RAY PA
University Hospital La Paz — Radiodiagnostics Department
Examination date: 22/01/2026  10:15
Report date: 22/01/2026  11:20
Patient: Martinez Lopez, Carlos  |  CIP: 2800001234
Requesting physician: Dr. Javier Ramos (Emergency)

TECHNIQUE
Posteroanterior projection in standing position, full inspiration.

FINDINGS
- Cardiothoracic index: 0.50 (normal). Cardiac silhouette at upper limit of normal.
- Mediastinum: no widening. Right and left hilum appear normal.
- Lung parenchyma: no consolidations, infiltrates or nodules. No signs of pulmonary
  oedema or vascular redistribution.
- Vascular markings: normal.
- Ribs and soft tissues: no relevant findings.
- Costophrenic angles: clear. No pleural effusion.

CONCLUSION
Chest X-ray without acute findings. No frank cardiomegaly.
No infiltrates or consolidations.

Dr. Roberto Sanchez Paloma — Radiologist
""",

        "nota_atencion_primaria_2026-02-11.txt": """\
PRIMARY CARE NOTE — CHRONIC DISEASE FOLLOW-UP
Las Rosas Health Centre  |  SERMAS
Date: 11/02/2026  09:30
Patient: Martinez Lopez, Carlos  |  CIP: 2800001234
Physician: Dr. Concepcion Alvarez Herrero — General Practitioner

REASON FOR VISIT
Hypertension and diabetes follow-up after emergency discharge for angina.
Medication adjustment as recommended by Cardiology.

HISTORY
Patient reports feeling better since the January episode. Following recommended
diet with poor adherence. Non-smoker. Occasional alcohol intake. Walks 30 minutes
daily as reported by patient.

VITAL SIGNS
BP: 144/88 mmHg  (measured after 5 min rest)
Second BP reading: 140/86 mmHg
HR: 78 bpm  |  Weight: 84 kg  |  Height: 172 cm  |  BMI: 28.4 kg/m2 (overweight)
Capillary glucose: 154 mg/dL (postprandial approximately 2 hours)

PLAN
- Adjust Losartan: switch to evening dose for better morning BP control.
- Reinforce low-calorie, low-sodium diet. Refer to nursing for education.
- Continue Metformin 850 mg twice daily.
- Request follow-up blood test in 4 weeks (HbA1c, lipids, renal function).
- Cardiology appointment confirmed for 10/03/2026.

Dr. Concepcion Alvarez Herrero
""",

        "nota_enfermeria_2026-03-10.txt": """\
CARDIOVASCULAR NURSING CARE PLAN
University Hospital La Paz — Ambulatory Cardiology Unit
Date: 10/03/2026
Patient: Martinez Lopez, Carlos  |  CIP: 2800001234
Responsible nurse: Maria Jesus Flores Torres

NURSING ASSESSMENT
59-year-old patient with ischemic heart disease, hypertension and type 2 diabetes.
Reports partial diet adherence. Good medication compliance per self-report.
Vital signs: BP 136/82 mmHg. HR 74 bpm. SpO2 98%. Weight 83 kg.

NURSING DIAGNOSES (NANDA)
- 00099 Ineffective health maintenance related to insufficient knowledge of
  cardiovascular diet.
- 00126 Deficient knowledge related to glycaemic control.

INTERVENTIONS (NIC)
- Education on DASH diet and sodium reduction.
- Training on recognising cardiovascular warning signs.
- Instruction on correct blood glucose self-monitoring technique.
- Reinforcement of antiplatelet therapy adherence (Aspirin).
- Measurement and recording of vital signs. Monthly weight monitoring.

GOALS (NOC)
- Target BP <130/80 mmHg at next review.
- HbA1c <7.0% in 3 months.
- BMI <27 kg/m2 at 6 months.

Maria Jesus Flores Torres  |  Specialist Cardiovascular Nurse
""",

        "historia_clinica_resumida_2026-03-11.txt": """\
SUMMARISED CLINICAL HISTORY (HCR)
University Hospital La Paz — SERMAS
Date of issue: 11/03/2026
Patient: Martinez Lopez, Carlos  |  CIP: 2800001234
Date of birth: 14/03/1966  |  Sex: Male  |  Municipality: Madrid

PERSONAL HISTORY
- Arterial hypertension (since 2015). On active treatment.
- Type 2 diabetes mellitus (since 2018). Suboptimal control (HbA1c 7.4%).
- Ischemic heart disease (since 2021). Stent in left anterior descending artery (2023).
- Percutaneous coronary angioplasty (02/2023).

ACTIVE PROBLEMS
1. Stable ischemic heart disease.
2. Arterial hypertension (partial control).
3. Type 2 diabetes mellitus (suboptimal control).
4. Dyslipidaemia (LDL 92 mg/dL, target <70).
5. Mild normocytic anaemia to be investigated.

CURRENT MEDICATION
- Losartan 50 mg — 1 tablet at night.
- Metformin 850 mg — 1 tablet twice daily with meals.
- Atorvastatin 40 mg — 1 tablet at night.
- Aspirin 100 mg — 1 tablet in the morning.
- Ezetimibe 10 mg — 1 tablet at night (added 10/03/2026).
- Sublingual nitroglycerin 0.4 mg — rescue if chest pain (as needed).

ALLERGIES AND INTOLERANCES
No known drug allergies.

RELEVANT CLINICAL EPISODES (last 12 months)
- 22-23/01/2026: Emergency for unstable angina. NSTEMI with necrosis ruled out.
  ECG and troponins normal. Discharged with treatment modification.
- 11/02/2026: Primary care check-up. Losartan dose adjusted.
- 10/03/2026: Cardiology review. Ezetimibe started. Echocardiogram requested.

VACCINATION
- Influenza: last dose 10/2025.
- COVID-19: complete schedule + booster 2024.
- Pneumococcal 23v: 2022.

Issued by: Dr. Isabel Mora Castellano — Cardiologist
""",
    },

    # ── 2800003456 · Miguel Torres Vega, healthy adult ───────────────────────
    "2800003456": {

        "nota_atencion_primaria_2025-01-15.txt": """\
PRIMARY CARE NOTE — ROUTINE CHECK-UP
Norte Health Centre  |  SERMAS
Date: 15/01/2025  10:00
Patient: Torres Vega, Miguel  |  CIP: 2800003456  |  Age: 34
Physician: Dr. Andres Ruiz Gimenez — General Practitioner

REASON FOR VISIT
Annual routine check-up. No current complaints.

HISTORY
No known chronic diseases. Non-smoker. Occasional alcohol (1-2 drinks/week).
Regular physical exercise (running 3 times/week, approximately 8 km each session).
Family history: father with hypertension (controlled with medication).

PHYSICAL EXAMINATION
BP: 118/74 mmHg  |  HR: 62 bpm  |  SpO2: 99%  |  Temp: 36.6 C
Weight: 74 kg  |  Height: 178 cm  |  BMI: 23.4 kg/m2 (normal)
Cardiopulmonary auscultation: regular rhythm, no murmurs. Clear lung fields.
Abdomen: soft, non-tender. No organomegaly.

COMPLEMENTARY TESTS
Blood test requested: full blood count, biochemistry, lipids, glucose, TSH.

ASSESSMENT
Healthy young adult. Appropriate weight and physical activity. Annual blood test
requested. Preventive cardiovascular risk counselling provided.

PLAN
- Annual blood test scheduled.
- Reinforce Mediterranean diet.
- Annual check-up in 12 months.
- No medication required at this time.

Dr. Andres Ruiz Gimenez — General Practitioner
""",

        "resultado_analitica_2025-01-15.txt": """\
LABORATORY REPORT — ROUTINE ANNUAL CHECK-UP
Norte Health Centre — Clinical Analysis
Date: 15/01/2025
Patient: Torres Vega, Miguel  |  CIP: 2800003456  |  Age: 34

FULL BLOOD COUNT
Haemoglobin: 15.4 g/dL  [RR: 13.5-17.5]  Normal
Haematocrit: 46.2%  Normal
MCV: 90 fL  Normal
WBC: 6.2 x10^9/L  Normal  |  Neutrophils: 58%
Platelets: 230 x10^9/L  Normal

BIOCHEMISTRY
Fasting glucose: 88 mg/dL  Normal
HbA1c: 5.2%  Normal
Creatinine: 0.87 mg/dL  |  eGFR: >90 mL/min/1.73m2  Normal
Total cholesterol: 172 mg/dL  Normal
LDL: 98 mg/dL  Normal (low cardiovascular risk)
HDL: 58 mg/dL  Normal (protective)
Triglycerides: 82 mg/dL  Normal
Sodium: 141 mEq/L  |  Potassium: 4.0 mEq/L  Normal
ALT: 22 U/L  |  AST: 20 U/L  Normal
TSH: 2.1 mIU/L  Normal

CONCLUSIONS
All parameters within normal limits. No clinical action required.
Recommend repeat in 12 months.
""",
    },

    # ── 2800005678 · Ana Garcia Ruiz, 42 y/o female — asthma + NSAID allergy ─
    "2800005678": {

        "nota_urgencias_2026-02-01.txt": """\
EMERGENCY DEPARTMENT REPORT
University Hospital La Paz — SERMAS
Date and time of visit: 01/02/2026  14:30
Patient: Garcia Ruiz, Ana
Date of birth: 08/09/1983  |  Sex: Female  |  CIP: 2800005678

CHIEF COMPLAINT
Progressive dyspnoea over the last 6 hours with audible wheezing. Patient
reports taking ibuprofen yesterday for a headache despite known allergy.
Persistent cough and difficulty completing sentences.

RELEVANT MEDICAL HISTORY
- Bronchial asthma (since 2010). Moderate persistent type.
- Allergy to non-steroidal anti-inflammatory drugs (NSAIDs) — DOCUMENTED.
  Reaction: bronchospasm and urticaria. Ibuprofen and naproxen confirmed.
- Current medication: Fluticasone/Salmeterol 250/25 mcg inhaler (2 puffs twice daily),
  Salbutamol 100 mcg inhaler (rescue as needed).
- No smoker. Textile industry worker.

PHYSICAL EXAMINATION
- BP: 126/78 mmHg  |  HR: 102 bpm  |  RR: 24 breaths/min  |  SpO2: 91% (room air)
- Temp: 36.8 C  |  Weight: 62 kg
- Alert, anxious. Using accessory respiratory muscles. Speaks in short phrases.
- Auscultation: diffuse bilateral expiratory wheezing. Prolonged expiration.

DIAGNOSTIC WORKUP
- Arterial blood gas (room air): pH 7.44, PaO2 68 mmHg, PaCO2 36 mmHg, SaO2 93%.
- Peak flow: 210 L/min (personal best: 380 L/min — 55% of predicted).
- Chest X-ray: pulmonary hyperinflation. No consolidation. No pneumothorax.

CLINICAL ASSESSMENT
Moderate-severe acute asthma exacerbation triggered by NSAID intake
(Ibuprofen self-administered despite documented allergy).

TREATMENT IN EMERGENCY DEPARTMENT
- Salbutamol 2.5 mg nebulised every 20 minutes x 3.
- Ipratropium bromide 0.5 mg nebulised.
- Methylprednisolone 60 mg IV bolus.
- Oxygen via Venturi mask at 35%.
- Continuous monitoring.

EVOLUTION
After 2 hours: SpO2 97%. RR 18. Peak flow 290 L/min (76%). Wheezing reduced.
Admitted to observation for 12 hours.

Dr. Patricia Medina Soto — Emergency Physician
""",

        "informe_alta_urgencias_2026-02-02.txt": """\
CLINICAL DISCHARGE REPORT — EMERGENCY DEPARTMENT
University Hospital La Paz — SERMAS
Date of discharge: 02/02/2026  09:00
Patient: Garcia Ruiz, Ana  |  CIP: 2800005678  |  Age: 42

DIAGNOSIS AT DISCHARGE
- Moderate-severe acute asthma exacerbation. Drug-induced (NSAID-Ibuprofen).
- Allergy to NSAIDs with bronchospasm. Confirmed and re-documented.

CLINICAL SUMMARY
Patient admitted with severe bronchospasm after inadvertent Ibuprofen intake.
Responded well to inhaled bronchodilator therapy and systemic corticosteroids.
Peak flow at discharge: 340 L/min (89% of personal best). SpO2 98% on room air.

DISCHARGE MEDICATION
1. Fluticasone/Salmeterol 250/25 mcg — 2 puffs twice daily (maintenance).
2. Salbutamol 100 mcg — 2 puffs as rescue (up to 4 times daily).
3. Oral prednisone 40 mg/day for 5 days, then discontinue.
4. Montelukast 10 mg at night (newly added — leukotriene receptor antagonist).

RECOMMENDATIONS
- ABSOLUTE contraindication to NSAIDs (Ibuprofen, Naproxen, Diclofenac, etc.).
  Safe analgesic alternative: Paracetamol 500-1000 mg.
- Carry medical alert card indicating NSAID allergy.
- Pulmonology outpatient appointment scheduled for 11/02/2026.
- Return to emergency if SpO2 <92%, peak flow <50% personal best, or no
  response to rescue inhaler within 20 minutes.

Dr. Patricia Medina Soto — Emergency Physician
""",

        "resultado_espirometria_2026-02-11.txt": """\
SPIROMETRY REPORT
University Hospital La Paz — Pulmonary Function Laboratory
Date: 11/02/2026
Patient: Garcia Ruiz, Ana  |  CIP: 2800005678  |  Age: 42  |  Sex: Female
Height: 163 cm  |  Weight: 62 kg  |  BMI: 23.3 kg/m2
Requesting physician: Dr. Carmen Valls — Pulmonologist

BASELINE SPIROMETRY (pre-bronchodilator)
FVC:         2.98 L  (83% predicted)
FEV1:        2.05 L  (74% predicted)
FEV1/FVC:    0.69
PEF:         5.2 L/s  (68% predicted)
FEF 25-75%:  1.82 L/s  (65% predicted)

POST-BRONCHODILATOR (after Salbutamol 400 mcg)
FVC:         3.12 L  (87% predicted)
FEV1:        2.48 L  (90% predicted)
FEV1/FVC:    0.79
FEV1 increase: +21% (+0.43 L) — SIGNIFICANT BRONCHODILATOR RESPONSE

BRONCHIAL REVERSIBILITY TEST: POSITIVE (FEV1 increase >12% and >200 mL)

INTERPRETATION
Mild obstructive ventilatory pattern with complete reversibility after
bronchodilator, consistent with bronchial asthma. Significant improvement
from emergency visit baseline (FEV1 74% vs 55% during acute episode).

CONCLUSIONS
Spirometry confirms partially controlled asthma. Full reversibility with
bronchodilator. Recommend maintaining current inhaled therapy and optimising
adherence. Bronchial provocation test not indicated at this time.

Dr. Carmen Valls Puigdomenech — Pulmonologist
""",

        "nota_evolucion_neumologia_2026-02-11.txt": """\
PULMONOLOGY OUTPATIENT FOLLOW-UP NOTE
University Hospital La Paz — SERMAS
Date: 11/02/2026  11:30
Patient: Garcia Ruiz, Ana  |  CIP: 2800005678
Physician: Dr. Carmen Valls Puigdomenech — Pulmonologist

REASON FOR VISIT
Follow-up after acute asthma exacerbation (01-02/02/2026).

HISTORY
Patient reports complete recovery from acute episode. No dyspnoea at rest.
Mild effort dyspnoea when climbing 2 flights of stairs. Uses rescue inhaler
approximately twice a week (adequate control threshold: <2 times/week borderline).
Confirms accidental Ibuprofen intake that triggered exacerbation. Now carries
NSAID allergy card.

PHYSICAL EXAMINATION
RR: 16 breaths/min  |  SpO2: 98% (room air)  |  HR: 78 bpm
Auscultation: mild end-expiratory wheezing bilaterally. No crackles.

SPIROMETRY (today): FEV1 74% predicted. See spirometry report.

ASTHMA CONTROL ASSESSMENT (ACQ-5 score: 1.6 — partially controlled)
- Nocturnal symptoms: 1 night/week.
- Daytime symptoms: 3-4 days/week.
- Rescue inhaler use: 2x/week.
- Activity limitation: mild.

CLINICAL ASSESSMENT
Partially controlled moderate persistent asthma. NSAID allergy confirmed.
Appropriate post-exacerbation recovery.

PLAN
1. Maintain Fluticasone/Salmeterol 250/25 mcg 2 puffs twice daily.
2. Add Montelukast 10 mg at night (continued from discharge).
3. Inhaler technique training (nurse session arranged).
4. Peak flow diary: record morning and evening values daily.
5. Provide written asthma action plan.
6. Review in 3 months. Earlier if ACQ >2.

Dr. Carmen Valls Puigdomenech — Pulmonologist
""",

        "resultado_laboratorio_2026-02-01.txt": """\
LABORATORY REPORT — URGENT BLOOD TEST
University Hospital La Paz — Clinical Analysis Department
Date: 01/02/2026  15:00
Patient: Garcia Ruiz, Ana  |  CIP: 2800005678

FULL BLOOD COUNT
Haemoglobin: 13.2 g/dL  Normal
WBC: 11.4 x10^9/L  HIGH (stress response / corticosteroid effect)
  Neutrophils: 78%  |  Lymphocytes: 14%  |  Eosinophils: 6% HIGH (atopy)
Platelets: 242 x10^9/L  Normal

BIOCHEMISTRY
Glucose: 108 mg/dL  (mild elevation — corticosteroid effect)
Creatinine: 0.82 mg/dL  Normal
Sodium: 138 mEq/L  |  Potassium: 3.9 mEq/L  Normal
CRP: 8.2 mg/L  Mildly elevated (inflammatory response)

SPECIFIC ALLERGY TESTS (previous outpatient results, included for reference)
Total IgE: 420 IU/mL  HIGH (atopic profile)
Specific IgE Aspirin/NSAIDs: 3.8 kU/L  POSITIVE

OBSERVATIONS
Leukocytosis likely related to acute stress and systemic corticosteroids.
Peripheral eosinophilia consistent with atopic background.
No evidence of infectious aetiology.
""",

        "nota_atencion_primaria_2026-03-01.txt": """\
PRIMARY CARE NOTE — POST-HOSPITALISATION FOLLOW-UP
Las Rosas Health Centre  |  SERMAS
Date: 01/03/2026  10:15
Patient: Garcia Ruiz, Ana  |  CIP: 2800005678
Physician: Dr. Concepcion Alvarez Herrero — General Practitioner

REASON FOR VISIT
Review one month after asthma exacerbation (February 2026).

HISTORY
Patient reports good general condition. Occasional mild dyspnoea on significant
exertion. Using rescue inhaler less than twice a week. No nocturnal symptoms
in the last 3 weeks. Carrying NSAID allergy card.

VITAL SIGNS
BP: 112/72 mmHg  |  HR: 76 bpm  |  SpO2: 99%  |  RR: 15 breaths/min
Weight: 61 kg  |  BMI: 22.9 kg/m2

PEAK FLOW TODAY: 365 L/min (96% personal best) — GOOD CONTROL

ASSESSMENT
Good asthma control post-exacerbation. Adequate medication adherence.
NSAID allergy re-documented in clinical history.

PLAN
- Continue current inhaled therapy unchanged.
- Continue Montelukast 10 mg at night.
- Next Pulmonology review scheduled (03/2026).
- Reinforce: Paracetamol is the only safe analgesic option.
- Routine annual blood test requested.

Dr. Concepcion Alvarez Herrero — General Practitioner
""",

        "historia_clinica_resumida_2026-03-01.txt": """\
SUMMARISED CLINICAL HISTORY
University Hospital La Paz — SERMAS
Date of issue: 01/03/2026
Patient: Garcia Ruiz, Ana  |  CIP: 2800005678
Date of birth: 08/09/1983  |  Sex: Female  |  Municipality: Madrid

PERSONAL HISTORY
- Bronchial asthma (since 2010). Moderate persistent type.
- Allergy to NSAIDs: Ibuprofen, Naproxen — confirmed anaphylaxis/bronchospasm.
  Safe alternative: Paracetamol.
- No tobacco use. Works in textile industry (potential occupational exposure).

ACTIVE PROBLEMS
1. Moderate persistent bronchial asthma. Partially controlled.
2. NSAID allergy with bronchospasm — ABSOLUTE CONTRAINDICATION.

CURRENT MEDICATION
- Fluticasone/Salmeterol 250/25 mcg — 2 puffs twice daily.
- Salbutamol 100 mcg — rescue inhaler.
- Montelukast 10 mg — 1 tablet at night.

ALLERGIES
NSAIDs (Ibuprofen, Naproxen, Diclofenac): bronchospasm and urticaria.
Paracetamol is the only safe analgesic.

RELEVANT CLINICAL EPISODES
- 01-02/02/2026: Emergency admission for acute asthma exacerbation triggered
  by accidental Ibuprofen intake. SpO2 91% on arrival. Treated with
  nebulised bronchodilators and IV methylprednisolone. Discharged 02/02/2026.
- 11/02/2026: Pulmonology follow-up. FEV1 74% with full bronchodilator reversibility.

VACCINATION
- Influenza: 10/2025.
- COVID-19: complete schedule + booster 2024.

Issued by: Dr. Carmen Valls Puigdomenech — Pulmonologist
""",
    },

    # ── 2800007890 · Laura Sanchez Moreno, preeclampsia pregnancy week 34 ────
    "2800007890": {

        "control_obstetrico_2026-03-20.txt": """\
OBSTETRIC CONTROL VISIT
University Hospital La Paz — Obstetrics and Gynaecology Department
Date: 20/03/2026  09:00
Patient: Sanchez Moreno, Laura  |  CIP: 2800007890  |  Age: 30
Gestational age: 33 weeks + 4 days  |  G2P1 (previous normal delivery 2022)
Physician: Dr. Rosa Fernandez Blanco — Obstetrician

REASON FOR VISIT
Routine third-trimester antenatal visit.

HISTORY
Patient reports mild headache for the last 3 days. Mild swelling in feet and
ankles in the afternoons. No visual disturbances. No epigastric pain.
No vaginal bleeding. Normal foetal movements.

VITAL SIGNS
BP: 146/94 mmHg  HIGH — repeated after 10 min rest: 144/92 mmHg  CONFIRMED HIGH
HR: 86 bpm  |  Temperature: 36.7 C  |  Weight: 78 kg (pre-pregnancy: 64 kg, +14 kg)
Peripheral oedema: ++ bilateral ankle oedema.

OBSTETRIC EXAMINATION
Uterine fundal height: 32 cm (slightly below expected for gestational age).
Foetal position: cephalic.
Cardiotocography (CTG): reactive. Foetal HR 145 bpm. No decelerations.
Ultrasound: BPD 84 mm. AC 296 mm. FL 65 mm. EFW: 2,020 g (P25).
Amniotic fluid: adequate (AFI 12 cm).

LABORATORY (from today's blood draw — results pending):
24-hour urine protein requested. CBC, liver function, renal function, uric acid.

CLINICAL ASSESSMENT
Blood pressure exceeds threshold. New-onset hypertension in pregnancy at week 33.
Preeclampsia criteria pending urine protein results (>300 mg/24h).

PLAN
- Admit to obstetric day unit for further monitoring and blood results.
- Antihypertensive therapy: Labetalol 100 mg twice daily started.
- Foetal surveillance: CTG twice daily. Ultrasound in 72 hours.
- Urgent referral if: BP >160/110 mmHg, visual disturbance, epigastric pain,
  severe headache, reduced foetal movements.

Dr. Rosa Fernandez Blanco — Obstetrician
""",

        "nota_urgencias_obstetrica_2026-04-01.txt": """\
OBSTETRIC EMERGENCY REPORT
University Hospital La Paz — Obstetrics and Gynaecology Department
Date and time: 01/04/2026  22:15
Patient: Sanchez Moreno, Laura  |  CIP: 2800007890  |  Age: 30
Gestational age: 35 weeks + 2 days  |  G2P1

CHIEF COMPLAINT
Severe frontal headache for the last 4 hours with visual blurring (phosphenes).
Epigastric pain. Patient on Labetalol since 20/03/2026.

VITAL SIGNS ON ARRIVAL
BP: 174/112 mmHg  SEVERE HYPERTENSION
HR: 98 bpm  |  SpO2: 98%  |  Temp: 36.9 C  |  Weight: 80 kg

CURRENT MEDICATION
Labetalol 100 mg twice daily (since 20/03/2026).

PHYSICAL EXAMINATION
Severe generalised oedema. Epigastric tenderness on palpation.
Deep tendon reflexes: hyperreflexia 3+.

OBSTETRIC EXAMINATION
CTG: foetal HR 148 bpm. Two late decelerations noted.
Bedside ultrasound: cephalic presentation. EFW approximately 2,300 g.

LABORATORY (STAT)
Haemoglobin: 10.8 g/dL  LOW
Platelets: 92,000/mcL  LOW — THROMBOCYTOPAENIA
AST: 98 U/L  HIGH  |  ALT: 112 U/L  HIGH
LDH: 680 U/L  HIGH
Creatinine: 1.2 mg/dL  (baseline 0.7)
Uric acid: 7.8 mg/dL  HIGH
Protein/creatinine ratio (spot urine): 3.8  SEVERE PROTEINURIA

CLINICAL ASSESSMENT
Severe preeclampsia with HELLP syndrome (Haemolysis, Elevated Liver enzymes,
Low Platelets). Foetal compromise (late decelerations on CTG).

MANAGEMENT
- IV access. Continuous maternal and foetal monitoring.
- Magnesium sulphate IV: 4 g loading dose over 20 min, then 1 g/hour infusion.
- IV Labetalol 20 mg bolus — BP target 140-150/90-100 mmHg.
- Corticosteroids for foetal lung maturation: Betamethasone 12 mg IM x 2 doses.
- Emergency Caesarean section indicated — obstetric team alerted.

Dr. Rosa Fernandez Blanco — Obstetrician on call
""",

        "nota_enfermeria_obstetrica_2026-04-01.txt": """\
OBSTETRIC NURSING NOTE — DELIVERY SUITE
University Hospital La Paz
Date: 01/04/2026  22:30
Patient: Sanchez Moreno, Laura  |  CIP: 2800007890
Nurse: Elena Castaño Vidal — Midwife

ASSESSMENT ON ARRIVAL
Patient brought from home by partner. Alert, distressed. Intense frontal headache.
BP on arrival: 174/112 mmHg. Patient connected to continuous monitoring.

CARE PROVIDED
- Two large-bore IV lines inserted (left forearm and right antecubital fossa).
- Blood samples drawn for STAT laboratories.
- Foetal CTG applied. Continuous monitoring.
- Urinary catheter inserted. Urine output: 35 mL/hour.
- IV magnesium sulphate infusion started per protocol.
- IV Labetalol 20 mg administered.
- Patient positioned in left lateral tilt.
- Informed patient and partner about severe preeclampsia diagnosis.
- Consent obtained for emergency Caesarean section.
- Pre-operative checklist completed. Anaesthesiology and paediatrics notified.
- Patient transferred to operating theatre at 23:10.

POST-OPERATIVE NOTE
Live male neonate delivered at 23:42. Birth weight 2,340 g. Apgar 7/9.
Transferred to neonatal unit for monitoring (prematurity).
Mother stable post-Caesarean. BP 148/94 mmHg at transfer to recovery.
Magnesium sulphate infusion continued for 24 hours.

Elena Castaño Vidal — Midwife
""",
    },

    # ── 2800009012 · Carmen Fernandez Iglesias, 74 y/o female — AF, HTA, osteoporosis
    "2800009012": {

        "nota_urgencias_2026-03-05.txt": """\
EMERGENCY DEPARTMENT REPORT
General University Hospital Gregorio Maranon — SERMAS
Date and time: 05/03/2026  08:45
Patient: Fernandez Iglesias, Carmen
Date of birth: 22/07/1951  |  Sex: Female  |  CIP: 2800009012

CHIEF COMPLAINT
Found by her daughter at home confused, disoriented and with left-sided facial
droop and left upper limb weakness. Symptoms onset approximately 3 hours ago.
No preceding trauma or fall reported.

RELEVANT MEDICAL HISTORY
- Atrial fibrillation (diagnosed 2018). On anticoagulation with Acenocoumarol.
  Last INR check (15/02/2026): 2.1 (therapeutic).
- Arterial hypertension (since 2010). On Ramipril 5 mg.
- Osteoporosis (diagnosed 2019). On Alendronate 70 mg/week + Calcium/Vitamin D.
- Mild cognitive impairment (MCI) — Geriatric assessment 2025.

PHYSICAL EXAMINATION
- BP: 182/104 mmHg  |  HR: 92 bpm irregular  |  SpO2: 95%  |  GCS: 13/15
- Temperature: 37.0 C
- NIHSS score: 8 (moderate stroke)
- Right gaze preference. Left facial palsy (central type). Left arm plegia (0/5).
  Left leg paresis (3/5). Left hemianopia. Dysarthria.
- Cardiopulmonary: irregular rhythm (AF). No murmurs. Bilateral crackles at lung bases.

DIAGNOSTIC WORKUP
- Urgent CT head (non-contrast): see radiology report.
- ECG: atrial fibrillation, ventricular rate 92 bpm. No acute ischaemic changes.
- Urgent labs: INR 2.4, Haemoglobin 11.8 g/dL, Glucose 136 mg/dL, Creatinine 1.1 mg/dL.
- Troponin I: negative.

CLINICAL ASSESSMENT
Ischaemic stroke in right hemisphere. Suspected cardioembolic origin (atrial
fibrillation). Anticoagulation ongoing (supratherapeutic INR 2.4 — IV thrombolysis
contraindicated).

MANAGEMENT
- Stroke unit admission.
- Anticoagulation suspended — reassess at 72 hours.
- Antihypertensive therapy titrated (BP target <180/105 mmHg acutely).
- Aspirin 100 mg temporarily (pending anticoagulation restart decision).
- Physiotherapy and speech therapy referral.

Dr. Miguel Santos Pereira — Emergency Physician / Neurologist on call
""",

        "informe_alta_urgencias_2026-03-05.txt": """\
CLINICAL DISCHARGE REPORT — STROKE UNIT
General University Hospital Gregorio Maranon — SERMAS
Admission: 05/03/2026  |  Discharge: 05/03/2026 (transferred to Neurology ward)
Patient: Fernandez Iglesias, Carmen  |  CIP: 2800009012  |  Age: 74

TRANSFER SUMMARY
Patient transferred from Emergency to Stroke Unit for continuous monitoring
and neurological rehabilitation.

DIAGNOSIS AT TRANSFER
- Acute ischaemic stroke. Right MCA territory (moderate: NIHSS 8).
- Suspected cardioembolic mechanism — known atrial fibrillation.
- Arterial hypertension. Osteoporosis. Mild cognitive impairment.

NEUROLOGICAL STATUS AT TRANSFER
GCS: 14/15. NIHSS: 7 (slight improvement).
Left hemiparesis persists. Left arm plegia improving to 1/5.
Mild dysarthria. Stable.

ACTIVE TREATMENT
- Acenocoumarol SUSPENDED.
- Aspirin 100 mg/day (temporary bridge).
- Ramipril 5 mg (continued, dose adjusted for acute phase).
- Alendronate and calcium/vitamin D: continued.
- DVT prophylaxis: enoxaparin 40 mg SC daily.
- Nasogastric tube for nutrition and medication (dysphagia assessment pending).

Dr. Miguel Santos Pereira — Attending Physician
""",

        "informe_tac_craneal_2026-03-05.txt": """\
CT HEAD REPORT — NON-CONTRAST
General University Hospital Gregorio Maranon — Radiology Department
Examination: 05/03/2026  09:15  |  Report: 05/03/2026  09:45
Patient: Fernandez Iglesias, Carmen  |  CIP: 2800009012
Requesting physician: Dr. Santos — Emergency

TECHNIQUE
Non-enhanced axial CT of the head. Contiguous 5 mm sections.

FINDINGS
- Right hemisphere: subtle hypodensity in the right middle cerebral artery (MCA)
  territory affecting cortical and subcortical regions of the right parietal and
  temporal lobes. Area approximately 4x3 cm. Consistent with acute ischaemia.
- No haemorrhagic transformation.
- No midline shift. No mass effect.
- Ventricles: mild generalised enlargement (cerebral atrophy, age-appropriate).
- No extra-axial collections.
- Cortical and subcortical hyperintensities (white matter disease, likely chronic
  small vessel disease).

CONCLUSION
CT findings consistent with acute right MCA ischaemic infarct. No haemorrhage.
Cerebral atrophy and chronic white matter disease consistent with patient age.
MRI with DWI recommended for extent confirmation.

Dr. Pilar Gomez Aranda — Neuroradiologist
""",

        "resultado_ecg_2026-03-05.txt": """\
ELECTROCARDIOGRAM REPORT
General University Hospital Gregorio Maranon
Date: 05/03/2026  08:50
Patient: Fernandez Iglesias, Carmen  |  CIP: 2800009012

PARAMETERS
- Rhythm: Atrial fibrillation.
- Ventricular rate: 92 bpm (irregular).
- QRS duration: 92 ms (normal).
- QTc: 430 ms (normal).
- No delta waves. No pre-excitation.

FINDINGS
Irregular rhythm consistent with atrial fibrillation. Controlled ventricular
response. No ST-segment elevation or depression. No acute ischaemic changes.
Left ventricular hypertrophy criteria (Sokolow-Lyon index 38 mm) — consistent
with hypertensive heart disease.

CONCLUSION
Atrial fibrillation with controlled ventricular rate. No acute ischaemic changes.
Left ventricular hypertrophy (hypertensive origin).

Dr. Alejandro Vega Montero — Cardiologist
""",

        "nota_medicina_interna_2026-03-08.txt": """\
INTERNAL MEDICINE WARD NOTE
General University Hospital Gregorio Maranon — SERMAS
Date: 08/03/2026  10:00
Patient: Fernandez Iglesias, Carmen  |  CIP: 2800009012
Physician: Dr. Clara Jimenez Rueda — Internal Medicine

REASON
Three days post-ischaemic stroke. Evaluation for anticoagulation restart.

NEUROLOGICAL EVOLUTION
NIHSS today: 5 (improving from 8 on admission).
Left arm: 2/5 strength. Left leg: 4/5. Mild dysarthria persists.
Walking with assistance. Physiotherapy twice daily.

ANTICOAGULATION ASSESSMENT
Stroke confirmed ischaemic (CT and MRI). No haemorrhagic transformation.
Embolic mechanism (atrial fibrillation) — high recurrence risk without
anticoagulation (CHA2DS2-VASc score: 6).
HAS-BLED score: 3 (moderate bleeding risk).
Decision: restart anticoagulation at day 7-14 post-stroke (guideline-based).
Switch from Acenocoumarol to DOAC (Direct Oral Anticoagulant): Rivaroxaban 20 mg
with evening meal. Easier monitoring, no INR required.

NUTRITIONAL STATUS
Swallowing assessment: dysphagia improving. Soft diet tolerated.
Nasogastric tube removed. Dietitian review for post-stroke nutritional plan.

OSTEOPOROSIS MANAGEMENT
Alendronate suspended during acute phase (dysphagia risk).
Calcium 500 mg + Vitamin D 800 IU daily maintained.
Denosumab 60 mg SC considered for restart when oral intake reliable.

COGNITIVE FUNCTION
Baseline mild cognitive impairment documented. Confusion improving.
Family counselling regarding post-stroke cognitive prognosis.

PLAN
- Rivaroxaban 20 mg daily to start on day 10 post-stroke (15/03/2026).
- Continue physiotherapy and speech therapy.
- Dietitian follow-up.
- CT head repeat at 2 weeks.
- Discharge planning: patient likely to need rehabilitation unit.

Dr. Clara Jimenez Rueda — Internal Medicine
""",

        "resultado_laboratorio_2026-03-12.txt": """\
LABORATORY REPORT — IN-HOSPITAL MONITORING
General University Hospital Gregorio Maranon
Date: 12/03/2026
Patient: Fernandez Iglesias, Carmen  |  CIP: 2800009012

FULL BLOOD COUNT
Haemoglobin: 11.8 g/dL  LOW (mild anaemia — likely chronic disease)
MCV: 86 fL  Normal
WBC: 8.2 x10^9/L  Normal
Platelets: 198 x10^9/L  Normal
INR: 1.3 (Acenocoumarol suspended — expected)

BIOCHEMISTRY
Glucose: 118 mg/dL  Mildly elevated
Creatinine: 1.0 mg/dL  |  eGFR: 58 mL/min/1.73m2  G3a (mild-moderate reduction)
Sodium: 140 mEq/L  |  Potassium: 4.2 mEq/L  Normal
CRP: 14 mg/L  Elevated (inflammatory response post-stroke)
LDH: 320 U/L  Mildly elevated

LIPID PROFILE
Total cholesterol: 198 mg/dL
LDL: 118 mg/dL  (statin therapy recommended post-stroke)
HDL: 52 mg/dL  Normal
Triglycerides: 140 mg/dL  Normal

BONE METABOLISM
Calcium: 9.1 mg/dL  Normal (on calcium supplement)
25-OH Vitamin D: 28 ng/mL  LOW (target >30 ng/mL)
PTH: 62 pg/mL  Mildly elevated (secondary hyperparathyroidism — vitamin D deficiency)

OBSERVATIONS
Mild anaemia consistent with chronic disease. Monitor.
Vitamin D insufficiency: increase supplementation to 2000 IU/day.
LDL elevated: statin therapy (Atorvastatin 40 mg) started post-stroke.
Renal function: CKD G3a — monitor and adjust medications accordingly.
""",

        "nota_atencion_primaria_2026-03-12.txt": """\
PRIMARY CARE COORDINATION NOTE
General University Hospital — Social Work and Primary Care Liaison
Date: 12/03/2026
Patient: Fernandez Iglesias, Carmen  |  CIP: 2800009012

DISCHARGE PLANNING
Coordination meeting with patient, daughter (primary caregiver) and social
worker to plan post-stroke rehabilitation and home care.

FUNCTIONAL STATUS
Barthel index: 45/100 (moderate dependence).
Requires assistance with: bathing, dressing, transfers.
Independent for: feeding (with soft diet), basic communication.

SOCIAL ASSESSMENT
Lives with daughter who works part-time. Appropriate housing (ground floor, wide
doorways). Telephone access available. No formal care previously.

DISCHARGE PLAN
1. Subacute rehabilitation unit — planned admission for 4-6 weeks.
2. Home physiotherapy 3x/week after rehabilitation unit discharge.
3. Primary care follow-up within 1 week of home return.
4. Medication reconciliation completed — simplified regimen for home use.

MEDICATION AT DISCHARGE
- Rivaroxaban 20 mg — 1 tablet with evening meal (start 15/03/2026).
- Ramipril 5 mg — 1 tablet in the morning.
- Atorvastatin 40 mg — 1 tablet at night (new).
- Aspirin 100 mg — to be DISCONTINUED when Rivaroxaban started.
- Calcium 500 mg + Vitamin D 2000 IU — 1 tablet daily.
- Alendronate suspended — review after 6 weeks.

Dr. Clara Jimenez Rueda / Social Worker: Maite Arroyo Saenz
""",

        "nota_enfermeria_2026-03-12.txt": """\
NURSING DISCHARGE SUMMARY
General University Hospital Gregorio Maranon
Date: 12/03/2026
Patient: Fernandez Iglesias, Carmen  |  CIP: 2800009012
Nurse: Juan Carlos Prieto Morales — Neurology Ward

FUNCTIONAL ASSESSMENT AT DISCHARGE
Mobility: walks with walking frame. Supervised.
Self-care: requires assistance with personal hygiene and dressing.
Communication: mild dysarthria — intelligible speech.
Swallowing: soft diet tolerates. No aspiration episodes last 48 hours.
Cognition: oriented to person and place. Mildly confused at night.
Pain: no complaints.

EDUCATION PROVIDED TO PATIENT AND FAMILY
- Stroke warning signs (FAST: Face drooping, Arm weakness, Speech difficulty, Time to call).
- Anticoagulation importance: never stop Rivaroxaban without medical advice.
- Fall prevention measures: non-slip mats, grab rails, clear walkways.
- Pressure area care: regular repositioning if immobile.
- Medication schedule explained and written summary provided.

FOLLOW-UP PLAN
- Rehabilitation unit on 13/03/2026.
- Cardiology outpatient appointment scheduled.
- Primary care review within 1 week of home discharge.

Juan Carlos Prieto Morales — Registered Nurse
""",

        "historia_clinica_resumida_2026-03-12.txt": """\
SUMMARISED CLINICAL HISTORY
General University Hospital Gregorio Maranon — SERMAS
Date of issue: 12/03/2026
Patient: Fernandez Iglesias, Carmen  |  CIP: 2800009012
Date of birth: 22/07/1951  |  Sex: Female  |  Municipality: Madrid

PERSONAL HISTORY
- Atrial fibrillation (since 2018). Anticoagulated — switching from Acenocoumarol
  to Rivaroxaban 20 mg.
- Arterial hypertension (since 2010). On Ramipril 5 mg.
- Osteoporosis (since 2019). Alendronate + Calcium/Vitamin D.
- Mild cognitive impairment (assessed 2025).

ACUTE EPISODE (March 2026)
Ischaemic stroke — right MCA territory. Cardioembolic mechanism (atrial fibrillation).
NIHSS on admission: 8. At discharge: 5.
Thrombolysis contraindicated (supratherapeutic anticoagulation at admission).

ACTIVE PROBLEMS
1. Right MCA ischaemic stroke — rehabilitation phase.
2. Atrial fibrillation — anticoagulation with Rivaroxaban.
3. Arterial hypertension — controlled with Ramipril.
4. Osteoporosis — calcium/vitamin D (Alendronate suspended).
5. Dyslipidaemia (new) — Atorvastatin 40 mg started.
6. Vitamin D insufficiency — supplementation increased.
7. Mild cognitive impairment — baseline, monitoring.

CURRENT MEDICATION
- Rivaroxaban 20 mg — 1 tablet with evening meal.
- Ramipril 5 mg — morning.
- Atorvastatin 40 mg — night.
- Calcium 500 mg + Vitamin D 2000 IU — daily.

ALLERGIES
No known drug allergies.

VACCINATION
- Influenza: 10/2025.
- Pneumococcal: 2023.

Issued by: Dr. Clara Jimenez Rueda — Internal Medicine
""",
    },
}


def main() -> None:
    txt_count = 0
    pdf_count = 0

    for cip, documents in DOCS.items():
        print(f"\nPatient {cip}:")
        for filename, content in documents.items():
            path = OUTPUT_BASE / cip / filename
            write_txt(path, content)
            txt_count += 1

            # Generate PDF for selected document types
            if any(t in filename for t in (
                "informe_alta", "resultado_laboratorio", "nota_urgencias",
                "resultado_espirometria", "control_obstetrico",
            )):
                pdf_path = path.with_suffix(".pdf")
                write_pdf(pdf_path, content)
                pdf_count += 1

    print(f"\n✓ Generated {txt_count} TXT files and {pdf_count} PDF files")
    print(f"  Output folder: {OUTPUT_BASE}")


if __name__ == "__main__":
    main()
