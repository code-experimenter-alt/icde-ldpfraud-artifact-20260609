PY ?= python3
MODE ?= paper

.PHONY: goal0 goal1 goal1b goal2 goal3 goal4 goal5 goal6 goal7 goal8 all paper_tables smoke artifact_index

goal0:
	$(PY) experiments/goal0_disclosure_baselines.py

goal1:
	$(PY) experiments/goal1_valuation.py --out experiments/results --seed 2026

goal1b:
	$(PY) experiments/goal1b_marketing_workloads.py --out experiments/results --seed 2026

goal2:
	$(PY) experiments/expanded_experiments.py --goal goal2

goal3:
	$(PY) experiments/goal3_pow_calibration.py

goal4:
	$(PY) experiments/goal4_incentives.py

goal5:
	$(PY) experiments/goal5_market_pipeline.py --out experiments/results --seed 2026

goal6:
	$(PY) experiments/goal6_robustness.py

goal7:
	@if [ "$(MODE)" = "estimate" ]; then \
		$(PY) experiments/goal7_throughput_cost.py --out experiments/results --allow-calibrated-estimate; \
	else \
		$(PY) experiments/goal7_throughput_cost.py --out experiments/results; \
	fi

goal8:
	$(PY) experiments/goal8_attacker_strategies.py

artifact_index:
	$(PY) experiments/expanded_experiments.py --goal artifact

paper_tables: goal0 goal1 goal1b goal2 goal3 goal4 goal5 goal6 goal7 goal8 artifact_index
	$(PY) experiments/make_experiment_figures.py

all: paper_tables

smoke:
	$(MAKE) paper_tables MODE=estimate
	$(PY) -c 'from pathlib import Path; req=["experiments/results/goal0_disclosure_regimes.csv","experiments/results/valuation_curves.csv","experiments/results/goal1b_conversion_sketch.csv","experiments/results/goal3_pow_calibration.csv","experiments/results/goal8_confusion_matrix.csv","figures/market_utility.pdf"]; missing=[p for p in req if not Path(p).exists()]; assert not missing, missing; print("smoke ok")'
