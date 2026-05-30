# RedDial — common dev/ops tasks. Run from server/.
.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install test lint fmt loopback campaign efficacy scorecard \
        evalset evalset-improve cekura-check cekura-evalset dashboard build deploy clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Sync deps from the lockfile (incl. dev)
	$(UV) sync --locked

test:  ## Run the curated test suite
	$(UV) run pytest tests/ -q

lint:  ## Ruff lint (matches CI)
	$(UV) run ruff check .

fmt:  ## Auto-fix lint
	$(UV) run ruff check --fix .

loopback:  ## One deterministic loopback breach (no keys)
	$(UV) run python -c "import loopback; r=loopback.run_loopback(); \
	print('BREACH' if r.breach else 'no breach','| grade',r.grade,'| turns',r.turns_to_first_leak)"

campaign:  ## Offline campaign -> scorecard.{json,html} (N=36, override: make campaign N=200)
	$(UV) run python campaign_runner.py --n $(or $(N),36) --persist

efficacy:  ## One honestly-labeled loopback efficacy artifact (results/)
	$(UV) run python efficacy_run.py --mode loopback

evalset:  ## Run the OFFLINE basic evalset -> PASS/FAIL + pass_rate (no keys)
	$(UV) run python -c "import evalset; r=evalset.run_evalset(); \
	print('PASS' if r['passed'] else 'FAIL','| pass_rate',r['pass_rate'])"

evalset-improve:  ## Improve until the basic evalset passes -> rounds_to_pass + final guardrail
	$(UV) run python -c "import evalset; r=evalset.improve_until_pass(); \
	print('PASS' if r['passed'] else 'FAIL','| rounds_to_pass',r['rounds_to_pass'],'| guardrail',r['final_guardrail'])"

cekura-check:  ## Probe Cekura connectivity (loud status, not a silent no-op)
	$(UV) run python -c "import cekura_integration as C; print(C.check_connection())"

cekura-evalset:  ## Publish the basic evalset + post its run verdict to Cekura (needs CEKURA_* in .env; graceful no-op without)
	$(UV) run python -c "from dotenv import load_dotenv; load_dotenv('.env'); \
import evalset, evalset_cekura as EC; \
pub=EC.publish_evalset(); print('scenarios published:', pub['published'], '| stub', pub['stub']); \
run=evalset.run_evalset(); print('evalset', 'PASS' if run['passed'] else 'FAIL', '| pass_rate', run['pass_rate']); \
res=EC.post_evalset_results(run); print('results posted:', res['posted'], '/', res['total'], '| stub', res['stub'])"

cekura-sync:  ## Push the persona pack + one loopback run to Cekura (needs CEKURA_* in .env)
	$(UV) run python -c "from dotenv import load_dotenv; load_dotenv('.env'); \
import cekura_integration as C, attack_library as A, loopback; \
reg=C.register_personas(A.ATTACKS); print('scenarios posted:', sum(1 for r in reg if r.get('posted')), '/', len(reg)); \
r=loopback.run_loopback(attack_id='authority_pretext', seconds_per_turn=9.0); \
print('observability posted:', C.post_observability(r, call_id='reddial-sync'))"

dashboard:  ## Run the OFFLINE control-plane API for the dashboard (then: cd ../frontend && npm run dev)
	@echo "RedDial dashboard — OFFLINE only (loopback; no live dialing)."
	@echo "API:      http://localhost:8080  (docs at /docs)"
	@echo "Frontend: in another shell run  ->  cd ../frontend && npm run dev"
	@echo "Starting uvicorn (Ctrl-C to stop)..."
	$(UV) run uvicorn api:app --port 8080

serve-attacker:  ## Run the attacker bot server (serves Twilio media at /ws). Needs NVIDIA+Gradium keys.
	REDDIAL_ROLE=attacker $(UV) run python bot.py -t twilio --proxy $(or $(PUBLIC_HOST),localhost:7860)

live-call:  ## Place ONE gated, consented live attack call. TO=+1XXXXXXXXXX (needs Twilio + dialing gate ON)
	@test -n "$(TO)" || (echo "set TO=+1XXXXXXXXXX (an allowlisted, consented number)"; exit 1)
	$(UV) run python efficacy_run.py --mode live --to $(TO) --consent

build:  ## Build the deploy image (override TAG / BASE). arm64 only — see DEPLOY.md.
	# The pipecat base ships linux/arm64 ONLY, so build for arm64 via buildx (QEMU
	# on amd64 hosts; native on Apple Silicon). Matches CI. BASE pins a REAL tag —
	# 0.0.8 never existed; 0.1.20-py3.12 is published. (Prod should pin the digest.)
	docker buildx build --platform linux/arm64 \
	  -t reddial:$(or $(TAG),dev) \
	  --build-arg PIPECAT_BASE=$(or $(BASE),dailyco/pipecat-base:0.1.20-py3.12) .

deploy:  ## Deploy to Pipecat Cloud (requires `pcc` auth + pcc-deploy.toml)
	pcc deploy

clean:  ## Remove generated artifacts
	rm -f scorecard.json scorecard.html
	rm -rf results transcripts/*/ __pycache__ tests/__pycache__
