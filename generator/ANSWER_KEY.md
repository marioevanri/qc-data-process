# Answer key

Spoilers. Read this only after your early warning and modeling evaluation is finished.

`data/truth/events.csv` lists the incidents drawn for this seed, one row per incident, with their dates, line, grade, material or supplier, effect size and a plain description. Possible kinds: spray dryer sensor bias, viscometer drift, bad oil lots, silent raw material supplier change, homogenizer wear, NIRS lamp change, CIP failure, overdue sensory control, one-day RND trial, cost-down reformulation, gas-saving production trial and a DKP reformulation. Not every factory has all of them.

RND's recipes are in `formulation_versions.csv` (% of dry solids per grade and version) and `mix_formula.csv` says which recipe each mix was made with. Nothing in `raw/`, `clean/` or `docs/` states a formula change. The only traces are production's own Remarks column, which QC doesn't read, and meeting notes that record symptoms with no cause.

The sensory control is renewed from recent production, so after one control cycle sensory stops seeing a permanent change. NIRS and lab history don't forget. Some documents written during an incident blame the wrong cause.

`mix_truth.csv` and `sample_truth.csv` hold true composition and drivers per mix and sample, including smaller natural issues that are not in `events.csv`. A detector alert that matches none of the events can still be one of these.


## truth/mix_truth

| Column | Meaning |
|---|---|
| outlet_temp_true | real outlet temperature |
| homog_eff | true homogenizer efficiency (1 = normal) |
| d43_um | true fat globule size |
| caseinate_func / smp_func | functionality of the protein lot used |
| oxid_intensity / burnt_intensity | true off-flavor drivers |
| lat_* | true sensory position vs the ideal product, in scale steps |
| feather_fail_p | true probability of failing the coffee test |

## truth/events

| Column | Meaning |
|---|---|
| id | EV01, EV02, ... in order of start date |
| kind | type of incident |
| start / end | when it was active (end empty = permanent) |
| line / grade / material / supplier / new_supplier | where it happened, when relevant |
| magnitude | effect size, meaning depends on kind |
| detail | plain description |
| other columns | kind-specific details (PV range, recipe delta, date QC found out, ...) |

## truth/formulation_versions

| Column | Meaning |
|---|---|
| version | recipe version, e.g. FMP-26-v2, NDC-35-T01 (trial) |
| kind | standard, reformulation, rnd_trial |
| valid_from / valid_to | dates the recipe was in use (a trial covers one day) |
| applies_to | all mixes, or the exact trial mixes |
| *_pct | % of dry solids: oil, GSS, caseinate, SMP, emulsifier, DKP (dipotassium phosphate), SiO2 |
| emulsifier | MDG, Lecithin, MDG + DATEM |
| note | what changed and why (RND's view, QC never received this) |

## truth/mix_formula

| Column | Meaning |
|---|---|
| mix_id | mix |
| formula_version | recipe version the mix was made with |

## truth/sample_truth

| Column | Meaning |
|---|---|
| contamination | fraction of previous grade in the sample |
| lat_* | true sensory latent of this sample |

## truth/control_truth

| Column | Meaning |
|---|---|
| base_* | true sensory latent of the control when fresh (it ages afterwards) |

## truth/raw_row_map

| Column | Meaning |
|---|---|
| raw_file / raw_row | raw file and 0-based data row |
| clean_key | key of the clean record (sample_uid@test_time for lab rows) |
| mess | mess applied to that row |
