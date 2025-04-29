INF_IMG      ?= influxdb:2.7
TELEG_IMG    ?= telegraf:1.30
NET          ?= influx-net
INF_CONT     ?= influxdb2
TELEG_CONT   ?= telegraf
ORG          ?= tlb-org
BUCKET       ?= tlb
USER         ?= admin
PASS         ?= password              # local dev only – change for prod
TELEG_CONF   ?= $(CURDIR)/telegraf.conf

# Abort if INFLUX_TOKEN is missing
ifndef INFLUX_TOKEN
$(error Please export INFLUX_TOKEN before running make)
endif

.PHONY: up
up: telegraf-start

.PHONY: net
net:
	@docker network create $(NET) 2>/dev/null || true

.PHONY: influx-start
influx-start: net
	-docker rm -f $(INF_CONT) >/dev/null 2>&1
	docker run -d --name $(INF_CONT) --network $(NET) -p 8086:8086 $(INF_IMG)
	@echo ">> waiting for InfluxDB…" ; sleep 5
	docker exec $(INF_CONT) influx setup --bucket $(BUCKET) --org $(ORG) \
	  --username $(USER) --password $(PASS) \
	  --token $$INFLUX_TOKEN --force >/dev/null || true

.PHONY: telegraf-start
telegraf-start: influx-start
	@test -f $(TELEG_CONF) || (echo "Missing $(TELEG_CONF)"; exit 1)
	-docker rm -f $(TELEG_CONT) >/dev/null 2>&1
	docker run -d --name $(TELEG_CONT) --network $(NET) \
	  -p 8089:8089/udp \
	  -v $(TELEG_CONF):/etc/telegraf/telegraf.conf:ro \
	  -e INFLUX_TOKEN=$$INFLUX_TOKEN \
	  $(TELEG_IMG)
	@echo ">> Telegraf listening on udp://0.0.0.0:8089"

# ─── helpers ──────────────────────────────────────────────────────────────────
.PHONY: influx-cli
influx-cli: ; docker exec -it $(INF_CONT) influx

.PHONY: stop
stop: ; -docker rm -f $(TELEG_CONT) $(INF_CONT) >/dev/null 2>&1
