# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Generate a 50-row synthetic discharge-note cohort for offline testing.

The output is intentionally NOT real MIMIC data — these notes are short
hand-crafted templates with subject_id values starting at 90001. Run this
file directly to regenerate the CSV:

    python evaluation/_synthetic_cohort.py

The seed is fixed so the output is deterministic and can be checked in.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

# --- Positive HF templates (hf_gold = 1) ---
_POS = [
    "DISCHARGE SUMMARY. {age}M with known HFrEF, EF 30% on echo. Admitted with acute decompensation, BNP 1820 pg/mL. NYHA III at baseline. Diuresed with IV furosemide. PMH significant for hypertension and diabetes. Discharge meds: carvedilol, lisinopril, spironolactone, furosemide. Follow-up with cardiology in 2 weeks.",
    "{age}F with dilated cardiomyopathy presenting with dyspnea on exertion. Echo confirmed EF 25%, severe global hypokinesis. BNP 2400. Diagnosis: acute on chronic systolic heart failure. Started on guideline-directed medical therapy. Bilateral crackles on exam, JVD elevated, 2+ lower extremity edema.",
    "Hospital course: {age}-year-old male admitted with worsening dyspnea over 1 week. Workup showed BNP 1650, echo with EF 35%, mild MR. NYHA II symptoms. Heart failure exacerbation likely 2/2 medication non-compliance. Diuresed 4L over admission.",
    "Patient with known systolic HF (EF 28%), admitted for fluid overload. Required 3 days of IV diuresis. BNP trended down from 2100 to 950. Started on entresto. Discharge weight 78 kg (admission 84 kg).",
    "{age}F with hypertensive cardiomyopathy, EF 32% on most recent echo. NYHA III symptoms with orthopnea and PND. Volume overloaded on admission. Diuresed and optimized on metoprolol succinate and losartan.",
    "Admission for acute decompensated heart failure. {age}M with ischemic CM (EF 30% post-MI 2015). BNP 3200 on admission. Required BiPAP for respiratory distress. Diuresed aggressively, now euvolemic.",
    "Patient with HFpEF, EF 55% but markedly elevated filling pressures on echo. BNP 850. NYHA III. Severe LA enlargement. Diuresis with torsemide. Follow up with HF clinic.",
    "{age}M known cardiomyopathy admitted with dyspnea at rest. EF 22% (worsened from 30%). BNP 4100. Initiated milrinone drip in CCU. Consideration of advanced HF therapies discussed.",
    "Hospital course: heart failure exacerbation in setting of new atrial fibrillation. EF 35% per echo this admission. BNP 1900. Rate-controlled with metoprolol. Diuresed with IV furosemide.",
    "{age}F admitted for HF exacerbation. Chronic systolic dysfunction, EF 30%. Was non-compliant with low-sodium diet during recent travel. Diuresed 6L over 4 days. Weight 92 kg then 86 kg.",
    "Patient with non-ischemic dilated CM, EF 25%, NYHA IV symptoms. ICD in place. Admitted with VT storm and decompensated HF. Stabilized in CCU. Discharged on amiodarone + carvedilol + lisinopril.",
    "Decompensated heart failure with reduced EF. Echo: EF 28%, severe LV dilatation. BNP 2750. Bilateral lower extremity edema 3+. Diuresed. JVD now flat. Cardiology follow-up in 1 week.",
    "{age}M with chronic systolic HF, EF 30%, presenting with worsening dyspnea and orthopnea. NYHA III. BNP 1500. Optimized on carvedilol, ARNI, MRA, SGLT2 inhibitor.",
    "Acute on chronic heart failure exacerbation. EF 32%. Pulmonary edema on CXR. Diuresed with IV furosemide drip. BNP downtrend. Discharge weight 82 kg.",
    "Patient with HFmrEF (EF 41%) and known HF symptoms. NYHA II-III. BNP 720. Admitted for symptom flare. Diuresed and discharged on guideline-directed therapy.",
    "{age}F admitted with class IV heart failure symptoms. EF 20%, severe MR. Inotropic support required. Discussed advanced therapies (LVAD vs transplant evaluation).",
    "Hospital course significant for HF exacerbation. {age}M with EF 25%, ICD. Admitted with shortness of breath, weight gain, and lower extremity edema. Diuresed aggressively.",
    "Patient with known cardiomyopathy (EF 30%) and chronic HF. Admitted for medication optimization after recent worsening of symptoms. NYHA III. BNP 1100.",
    "{age}M presenting with acute decompensated HF. EF 27%. Sequelae of prior MI. Diuresed in unit. Discharge BNP 880.",
    "Heart failure with reduced ejection fraction. EF 33% per cardiac MRI. NYHA III. BNP 1300. Diuresed and discharged on quad therapy.",
    "Admission for acute heart failure. EF 24% on bedside echo. Severe biventricular dysfunction. Required temporary mechanical support consultation.",
    "{age}F with peripartum cardiomyopathy. EF 30% at diagnosis 6 months ago, now 35%. NYHA II. BNP 600. Continuing guideline-directed therapy.",
    "Patient presented with NYHA IV HF symptoms. EF 22%. Diuresed. Initiated on entresto + dapagliflozin in addition to carvedilol.",
    "Recurrent HF exacerbation. EF 28%. BNP 2200. Diuresed 5L. Cardiology consult recommended LifeVest and HF clinic follow-up.",
    "{age}M known HFrEF EF 30%, ischemic etiology. Admitted with volume overload after holding diuretics during recent illness. Diuresed and stabilized.",
]

# --- Negative templates (hf_gold = 0) ---
_NEG = [
    "DISCHARGE SUMMARY. {age}F admitted for cellulitis of the left lower extremity. No cardiac history. EF 65% on prior echo from 2 years ago. BNP not measured. Treated with IV vancomycin then oral cephalexin. Tolerated diet, ambulating well.",
    "Outpatient referral note. {age}M for annual physical. Asymptomatic. No SOB, no edema, no chest pain. ECG normal. No echo on file. PMH significant for well-controlled hypertension and hyperlipidemia.",
    "Patient admitted with community-acquired pneumonia. {age}F. Treated with ceftriaxone and azithromycin. EF normal per prior echo. No signs of cardiac dysfunction. Discharged on oral antibiotics.",
    "Hospital course: {age}M admitted for acute cholecystitis. Underwent laparoscopic cholecystectomy without complication. Cardiac risk stratification revealed normal stress test. Discharged on POD2.",
    "Admitted for evaluation of new-onset abdominal pain. {age}F. CT abdomen showed appendicitis. Status post laparoscopic appendectomy. Recovery unremarkable. No cardiac issues during admission.",
    "{age}M evaluated for headache and visual changes. MRI brain unremarkable. Diagnosis: migraine with aura. No cardiac workup indicated. PMH: only seasonal allergies. Discharged home.",
    "Patient with acute kidney injury secondary to dehydration. {age}F. Creatinine 2.4 on admission, returned to 0.9 with IV fluids. No history of HF or cardiac dysfunction. Renal function fully recovered.",
    "Hospital course: {age}M admitted for elective hip replacement. Pre-op cardiac evaluation normal. Surgery without complication. Discharged to rehab POD3.",
    "Admission for management of diabetes ketoacidosis. {age}F type 1 DM. Treated with insulin drip per protocol. No cardiac findings. Echo not indicated.",
    "Patient {age}M with COPD exacerbation. Treated with steroids, bronchodilators, antibiotics. Pulmonary function tests showed obstructive pattern. No cardiac component to dyspnea. Echo normal.",
    "{age}F admitted for migraine with vomiting and dehydration. Treated with IV fluids and antiemetics. No cardiac history. Discharged after 24 hours.",
    "Hospital course: viral gastroenteritis. {age}M presented with diarrhea and dehydration. Stable hemodynamically throughout. No cardiac issues. Discharged home with oral rehydration.",
    "{age}F admitted for elective colonoscopy (history of family colon cancer). Procedure unremarkable. Two small polyps removed. No cardiac workup needed.",
    "Patient with acute sinusitis with periorbital cellulitis. {age}M. IV antibiotics. No cardiac symptoms or workup performed.",
    "{age}F admitted for evaluation of syncope. Comprehensive cardiac workup including echo, stress test, and event monitor showed no abnormalities. EF 60%. Diagnosed with vasovagal syncope.",
    "Hospital course: {age}M with new diagnosis of seizure disorder. EEG showed temporal lobe focus. No cardiac involvement. Started on levetiracetam.",
    "Patient admitted for management of cellulitis with mild sepsis. {age}F. Resolved with antibiotics. Cardiac function preserved throughout admission. Echo from 2018 normal.",
    "{age}M evaluated for chronic back pain. MRI showed degenerative disc disease. Pain controlled with PT and NSAIDs. No cardiac history or symptoms.",
    "Admission for management of acute alcoholic hepatitis. {age}F. No cardiac dysfunction; echo showed EF 65%. Discharged with addiction medicine follow-up.",
    "{age}M admitted for acute UTI with bacteremia. Treated with IV antibiotics. No cardiac findings or workup needed.",
    "Patient with bilateral lower extremity DVT. {age}F. Started on anticoagulation. Workup for thrombophilia pending. Cardiac function preserved.",
    "Hospital course: {age}M admitted for elective shoulder arthroscopy. Pre-op clearance normal. Procedure uneventful. Discharged same day.",
    "{age}F with newly diagnosed Graves' disease. Started on methimazole. Cardiac evaluation showed mild sinus tachycardia consistent with hyperthyroidism, otherwise normal.",
    "Patient with rheumatoid arthritis flare. {age}M. Treated with steroids and DMARDs. No cardiac involvement. Echo normal.",
    "Admission for elective inguinal hernia repair. {age}M. Pre-op cardiac clearance unremarkable. Discharged POD0.",
]


def generate(out_path: Path = None, seed: int = 42, n: int = 50) -> Path:
    """Generate a deterministic synthetic cohort CSV.

    Args:
        out_path: where to write the CSV. Defaults to evaluation/synthetic_cohort.csv.
        seed: RNG seed (the chosen value is checked into git via the default).
        n: total row count. Must be even (split 50/50 positive/negative).
    """
    if n % 2 != 0:
        raise ValueError("n must be even (half positive, half negative)")
    out_path = out_path or (Path(__file__).parent / "synthetic_cohort.csv")
    rng = random.Random(seed)

    rows = []
    for i in range(n // 2):
        rows.append({
            "subject_id": 90001 + i,
            "hadm_id": 100001 + i,
            "note_id": f"D{100001 + i}",
            "note_date": f"2018-{1 + (i % 12):02d}-15 09:30:00",
            "text": rng.choice(_POS).format(age=rng.randint(45, 85)),
            "hf_gold": 1,
        })
        rows.append({
            "subject_id": 90501 + i,
            "hadm_id": 200001 + i,
            "note_id": f"D{200001 + i}",
            "note_date": f"2018-{1 + ((i + 6) % 12):02d}-15 09:30:00",
            "text": rng.choice(_NEG).format(age=rng.randint(25, 80)),
            "hf_gold": 0,
        })

    rng.shuffle(rows)
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["subject_id", "hadm_id", "note_id", "note_date", "text", "hf_gold"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return out_path


if __name__ == "__main__":
    p = generate()
    print(f"wrote {p}")
