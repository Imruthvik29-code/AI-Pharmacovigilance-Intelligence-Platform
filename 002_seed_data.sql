-- Phase 1: Database
-- Seed data — curated starter set of reference drugs, interaction rules,
-- and ADR rules. Small and well-established on purpose (per spec section 3:
-- "curated drug/interaction set, schema built to scale later"). Sources
-- noted per row; expand this list over time rather than redesigning it.

-- ── Reference Drugs ─────────────────────────────────────────────────────
insert into reference_drugs (id, name, generic_name, drug_class) values
  (gen_random_uuid(), 'Warfarin', 'warfarin', 'Anticoagulant'),
  (gen_random_uuid(), 'Aspirin', 'acetylsalicylic acid', 'NSAID / Antiplatelet'),
  (gen_random_uuid(), 'Ibuprofen', 'ibuprofen', 'NSAID'),
  (gen_random_uuid(), 'Lisinopril', 'lisinopril', 'ACE Inhibitor'),
  (gen_random_uuid(), 'Simvastatin', 'simvastatin', 'Statin'),
  (gen_random_uuid(), 'Amiodarone', 'amiodarone', 'Antiarrhythmic'),
  (gen_random_uuid(), 'Metformin', 'metformin', 'Biguanide / Antidiabetic'),
  (gen_random_uuid(), 'Sertraline', 'sertraline', 'SSRI'),
  (gen_random_uuid(), 'Tramadol', 'tramadol', 'Opioid Analgesic'),
  (gen_random_uuid(), 'Spironolactone', 'spironolactone', 'Potassium-sparing Diuretic'),
  (gen_random_uuid(), 'Levothyroxine', 'levothyroxine', 'Thyroid Hormone'),
  (gen_random_uuid(), 'Omeprazole', 'omeprazole', 'Proton Pump Inhibitor');

-- ── Interaction Rules ────────────────────────────────────────────────────
-- Warfarin + Aspirin -> additive bleeding risk (well-established, FDA label)
insert into interaction_rules (id, drug_a_id, drug_b_id, severity, mechanism, recommendation, source)
select gen_random_uuid(), a.id, b.id, 'severe',
  'Additive antiplatelet/anticoagulant effect increases bleeding risk.',
  'Avoid combination where possible; if co-prescribed, monitor INR and watch for bleeding signs closely.',
  'FDA Label'
from reference_drugs a, reference_drugs b
where a.name = 'Warfarin' and b.name = 'Aspirin';

-- Warfarin + Ibuprofen -> increased bleeding risk + reduced renal clearance of warfarin metabolites
insert into interaction_rules (id, drug_a_id, drug_b_id, severity, mechanism, recommendation, source)
select gen_random_uuid(), a.id, b.id, 'severe',
  'NSAIDs impair platelet function and can displace warfarin from protein binding, raising bleeding risk.',
  'Avoid concurrent use; consider acetaminophen as an alternative analgesic.',
  'FDA Label'
from reference_drugs a, reference_drugs b
where a.name = 'Warfarin' and b.name = 'Ibuprofen';

-- Simvastatin + Amiodarone -> increased myopathy/rhabdomyolysis risk (CYP3A4 inhibition)
insert into interaction_rules (id, drug_a_id, drug_b_id, severity, mechanism, recommendation, source)
select gen_random_uuid(), a.id, b.id, 'severe',
  'Amiodarone inhibits CYP3A4 metabolism of simvastatin, raising plasma levels and myopathy/rhabdomyolysis risk.',
  'Limit simvastatin dose to 20mg/day when combined with amiodarone, per FDA guidance.',
  'FDA Label'
from reference_drugs a, reference_drugs b
where a.name = 'Simvastatin' and b.name = 'Amiodarone';

-- Lisinopril + Spironolactone -> hyperkalemia risk (both raise potassium)
insert into interaction_rules (id, drug_a_id, drug_b_id, severity, mechanism, recommendation, source)
select gen_random_uuid(), a.id, b.id, 'moderate',
  'Both drugs reduce potassium excretion, raising risk of clinically significant hyperkalemia.',
  'Monitor serum potassium and renal function periodically during combined use.',
  'FDA Label'
from reference_drugs a, reference_drugs b
where a.name = 'Lisinopril' and b.name = 'Spironolactone';

-- Lisinopril + Ibuprofen -> reduced antihypertensive effect + renal risk
insert into interaction_rules (id, drug_a_id, drug_b_id, severity, mechanism, recommendation, source)
select gen_random_uuid(), a.id, b.id, 'moderate',
  'NSAIDs reduce prostaglandin-mediated renal blood flow, blunting ACE inhibitor effect and raising acute kidney injury risk.',
  'Use lowest effective NSAID dose/duration; monitor blood pressure and renal function.',
  'FDA Label'
from reference_drugs a, reference_drugs b
where a.name = 'Lisinopril' and b.name = 'Ibuprofen';

-- Sertraline + Tramadol -> serotonin syndrome risk
insert into interaction_rules (id, drug_a_id, drug_b_id, severity, mechanism, recommendation, source)
select gen_random_uuid(), a.id, b.id, 'severe',
  'Both increase serotonergic activity; combined use raises risk of serotonin syndrome.',
  'Avoid combination if possible; if necessary, educate patient on serotonin syndrome symptoms and monitor closely.',
  'FDA Label'
from reference_drugs a, reference_drugs b
where a.name = 'Sertraline' and b.name = 'Tramadol';

-- Omeprazole + Warfarin -> potential increased warfarin effect
insert into interaction_rules (id, drug_a_id, drug_b_id, severity, mechanism, recommendation, source)
select gen_random_uuid(), a.id, b.id, 'mild',
  'Omeprazole may modestly inhibit warfarin metabolism via CYP2C19, slightly raising INR.',
  'Monitor INR after initiating or stopping omeprazole in patients on warfarin.',
  'FDA Label'
from reference_drugs a, reference_drugs b
where a.name = 'Omeprazole' and b.name = 'Warfarin';

-- ── ADR Rules ────────────────────────────────────────────────────────────
insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Bleeding / bruising', 'severe', 'common', 'FDA Label'
from reference_drugs where name = 'Warfarin';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'GI upset / gastritis', 'moderate', 'common', 'FDA Label'
from reference_drugs where name = 'Aspirin';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'GI bleeding / ulceration', 'severe', 'uncommon', 'FDA Label'
from reference_drugs where name = 'Ibuprofen';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Dry cough', 'mild', 'common', 'FDA Label'
from reference_drugs where name = 'Lisinopril';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Hyperkalemia', 'moderate', 'uncommon', 'FDA Label'
from reference_drugs where name = 'Lisinopril';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Myopathy / muscle pain', 'moderate', 'uncommon', 'FDA Label'
from reference_drugs where name = 'Simvastatin';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Rhabdomyolysis', 'severe', 'rare', 'FDA Label'
from reference_drugs where name = 'Simvastatin';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Thyroid dysfunction', 'moderate', 'uncommon', 'FDA Label'
from reference_drugs where name = 'Amiodarone';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'GI upset / diarrhea', 'mild', 'common', 'FDA Label'
from reference_drugs where name = 'Metformin';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Lactic acidosis', 'severe', 'rare', 'FDA Label'
from reference_drugs where name = 'Metformin';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Nausea', 'mild', 'common', 'FDA Label'
from reference_drugs where name = 'Sertraline';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Seizure risk (dose-dependent)', 'severe', 'rare', 'FDA Label'
from reference_drugs where name = 'Tramadol';

insert into adr_rules (id, drug_id, reaction_description, severity, frequency_class, source)
select gen_random_uuid(), id, 'Hyperkalemia', 'moderate', 'uncommon', 'FDA Label'
from reference_drugs where name = 'Spironolactone';
