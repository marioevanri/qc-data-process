# Data dictionary

Clean tables in `data/clean/`. Raw files carry the same information with department-specific headers. The `data/truth/` tables are described in `ANSWER_KEY.md`, which contains spoilers.

## Keys used everywhere

| Column | Meaning |
|---|---|
| mix_id | batch_no + '-' + mix letter, e.g. 25090834P2-B |
| batch_no | YYMMDD + grade code + line code |
| sample_uid | mix_id + sampling point, e.g. 25090834P2-B2 |
| sample_code | mix letter + point (1 start, 2 middle, 3 end) |
| prod_date | production date (a production day runs 07:00 to 07:00) |
| line | P1 Plant 1, P2 Plant 2, RT retail line |
| grade | product grade |
| analyst_id | KimFis analyst code (master_staff) |

## rm_receiving

| Column | Meaning |
|---|---|
| receipt_id | receiving record id |
| received_at | arrival time |
| material_code | RM-OIL-HCO, RM-OIL-PO, RM-GSS, RM-CAS, RM-SMP |
| supplier_lot | supplier's lot number |
| internal_lot | internal lot, KODE-YYMMDD-NN, used in production_mix_log |
| qty_kg | delivered quantity |
| coa_* | value on the supplier COA |
| qc_* | value measured by QC (blank = not tested) |
| decision | Accept / Conditional / Reject (SOP-QC-001) |
| remarks | reason for Conditional or Reject |
| qc_release_date | date the lot can be used |

## production_mix_log

| Column | Meaning |
|---|---|
| shift | 1 = 07-15, 2 = 15-23, 3 = 23-07 |
| start / end | mix start and finish on the dryer |
| mix_kg | mix size |
| oil_lot / gss_lot / protein_lot | internal lots used |
| inlet_temp | dryer inlet reading (C) |
| outlet_temp | dryer outlet sensor reading (C), not necessarily the true outlet |
| homog_p1_bar / homog_p2_bar | homogenizer gauge readings |
| feed_solids | feed total solids (%) |
| emulsion_temp | emulsion tank temperature (C) |

## dryer_logger

| Column | Meaning |
|---|---|
| timestamp | 30 minute reading |
| * | same sensors as the mix log |

## qc_lab_kimfis

| Column | Meaning |
|---|---|
| test_time | time of the test |
| moisture_pct | moisture analyzer, all points |
| viscosity_cp | 20 % solution at 25 C, all points |
| brix | same solution, all points |
| fat_pct | point 2 only |
| protein_pct | point 2, day shift only |
| bulk_density | g/ml, point 2 |
| solubility_ml | insolubility index, point 2 |
| wettability_s | seconds, point 2 |
| L_star | color, point 2 |
| ph | solution pH, point 2 |
| coffee_test | feathering test, point 2, coffee grades only |
| is_retest | True for the re-measurement of an out-of-spec result |
| retest_of | which parameters triggered the retest |

## nirs_results

| Column | Meaning |
|---|---|
| scan_id | instrument scan number |
| is_control | True for the reference control scanned before each grade run |
| control_id | control scanned (controls only) |
| pred_* | instrument model predictions |

## nirs_spectra.csv.gz

| Column | Meaning |
|---|---|
| scan_id | joins to nirs_results |
| nm_<wl> | log(1/R) absorbance at that wavelength |

## sensory_kimfis

| Column | Meaning |
|---|---|
| control_id | reference control in use |
| score_* | -2 to +2 vs control (creamy, mouthfeel, milky, sweetness) |
| off_flavor / off_flavor_type | oxid (tengik), burnt (gosong), mixgrade (rasa campur), random |
| grade_result | Pass, TP1+/-, TP2+/-, TP3 (SOP-QC-005) |
| notes | analyst's note |

## sensory_verifikator

| Column | Meaning |
|---|---|
| test_time | H+1 re-check time |
| verifikator_id | VR01 / VR02 |
| kimfis_grade | what KimFis gave the same sample |
| score_* / grade_result | verifikator's own result |

## sensory_controls

| Column | Meaning |
|---|---|
| control_id | CTRL-<grade code>-NNN |
| source_batch | batch the control was taken from |
| start_use / due_date / end_use | in use from, due for replacement, actually replaced |
| extended | kept past its due date |

## retail_transition_samples

| Column | Meaning |
|---|---|
| transition_id | one grade change on RT (not in raw) |
| sample_seq | sample number after the change (not in raw) |
| sample_time | clock time the sample was taken |
| result | Pass / Belum Pass |
| handling | what happened to not-pass powder |

## micro_results

| Column | Meaning |
|---|---|
| received_lab / result_date | lab receipt and result (H+3) |
| tpc_cfu_g | total plate count |
| coliform_cfu_g, coliform_lt10 | coliform and below-LOD flag |
| ym_cfu_g, ym_lt10 | yeast and mold |
| micro_status | Pass / Fail (MS / TMS in raw) |
| fail_reason | which parameter failed |

## release_history

| Column | Meaning |
|---|---|
| status_time | when the status was set |
| status | QUARANTINE, HOLD, RELEASE, RELEASE-URGENT, BLEND, REWORK, REJECT, RECALL |
| reason | why |
| decided_by | who |

## shipments

| Column | Meaning |
|---|---|
| do_no | delivery order |
| mixes | mix letters shipped |
| qty_kg | shipped quantity |

## complaints

| Column | Meaning |
|---|---|
| category | complaint category |
| description | customer's words |
| justified | investigation outcome |
| status | Open / Closed |

## All columns per clean table

- complaints: complaint_id, received_date, customer_id, customer_name, do_no, batch_no, grade, category, description, qty_affected_kg, justified, status
- dryer_logger: timestamp, line, inlet_temp, outlet_temp, homog_p1_bar, homog_p2_bar, emulsion_temp, ambient_rh
- master_customers: customer_id, name, segment, grades
- master_materials: material_code, material_name
- master_products: grade, grade_code, name, segment, lines, oil, protein_source, fat_target, protein_target, fat_min, fat_max, protein_min, moisture_max, visc_min, visc_max, bulk_min, bulk_max, solubility_max, wettability_max, L_min, ph_min, ph_max, tpc_max, ym_max, coffee_test, control_days, spec_rev, valid_from, valid_to
- master_staff: staff_id, name, role, start, end
- master_suppliers: supplier_id, name, country
- micro_results: batch_no, prod_date, line, grade, received_lab, result_date, salmonella_result_date, tpc_cfu_g, coliform_cfu_g, coliform_lt10, ym_cfu_g, ym_lt10, ecoli, salmonella, micro_status, fail_reason
- nirs_results: scan_id, scan_time, line, grade, prod_date, is_control, control_id, sample_uid, pred_moisture, pred_fat, pred_protein, instrument
- production_mix_log: mix_id, batch_no, prod_date, line, grade, mix_letter, shift, start, end, mix_kg, oil_lot, gss_lot, protein_lot, inlet_temp, outlet_temp, homog_p1_bar, homog_p2_bar, feed_solids, emulsion_temp
- qc_lab_kimfis: sample_uid, batch_no, line, grade, prod_date, sample_code, sample_time, test_time, analyst_id, moisture_pct, viscosity_cp, brix, fat_pct, protein_pct, bulk_density, solubility_ml, wettability_s, L_star, ph, coffee_test, is_retest, retest_of
- release_history: mix_id, batch_no, grade, line, status_time, status, reason, decided_by
- retail_transition_samples: transition_id, prod_date, line, from_grade, to_grade, batch_no, mix_letter, sample_seq, sample_time, analyst_id, result, handling
- rm_receiving: receipt_id, received_at, material_code, material_name, supplier_id, supplier_name, supplier_lot, internal_lot, qty_kg, coa_ffa, coa_pv, coa_moisture, coa_color_red, qc_ffa, qc_pv, qc_moisture, qc_color_red, decision, remarks, inspector, qc_release_date, coa_de, coa_ph, qc_de, qc_ph, coa_protein, qc_protein, coa_fat, coa_solubility, coa_tpc, qc_fat, qc_solubility, qc_tpc
- sensory_controls: control_id, grade, source_batch, start_use, due_date, end_use, extended, note
- sensory_kimfis: sample_uid, batch_no, line, grade, prod_date, sample_code, sample_time, test_time, analyst_id, control_id, score_creamy, score_mouthfeel, score_milky, score_sweetness, off_flavor, off_flavor_type, grade_result, notes
- sensory_verifikator: sample_uid, batch_no, grade, prod_date, sample_code, test_time, verifikator_id, score_creamy, score_mouthfeel, score_milky, score_sweetness, off_flavor, off_flavor_type, grade_result, kimfis_grade, notes
- shipments: do_no, ship_date, customer_id, customer_name, batch_no, grade, mixes, qty_kg
