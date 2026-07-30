#!/usr/bin/with-contenv bashio
set -e

arch="$(apk --print-arch)"
case "$arch" in \
    aarch64) arch='arm64' ;; \
    armhf) arch='armhf' ;; \
    armv7) arch='arm' ;; \
    x86_64) arch='x86_64' ;; \
    x86) arch='x86' ;; \
    *) bashio::log.warning "Unknown architecture: ${arch}, using as-is" ;; \
esac
ulimit -n 4096
bashio::log.info "AirSendWebService arch: ${arch}"

# MQTT credentials — priority order:
#   1. Manual addon config (mqtt.host explicitly set by the user)
#   2. Supervisor-injected env vars MQTT__HOST/PORT/USERNAME/PASSWORD (services: mqtt:need)
#   3. bashio::services mqtt (older Supervisor fallback)
#   4. Hardcoded defaults (last resort)
_mqtt_host_manual=$(bashio::config 'mqtt.host' '')
if [[ -n "${_mqtt_host_manual}" ]] && [[ "${_mqtt_host_manual}" != "null" ]]; then
    export MQTT_HOST="${_mqtt_host_manual}"
    export MQTT_PORT=$(bashio::config 'mqtt.port' '1883')
    export MQTT_USER=$(bashio::config 'mqtt.username' '')
    export MQTT_PASS=$(bashio::config 'mqtt.password' '')
    bashio::log.info "MQTT credentials loaded from addon config (host=${MQTT_HOST}:${MQTT_PORT})"
elif [[ -n "${MQTT__HOST:-}" ]]; then
    export MQTT_HOST="${MQTT__HOST}"
    export MQTT_PORT="${MQTT__PORT:-1883}"
    export MQTT_USER="${MQTT__USERNAME:-}"
    export MQTT_PASS="${MQTT__PASSWORD:-}"
    bashio::log.info "MQTT credentials loaded from Supervisor environment (host=${MQTT_HOST}:${MQTT_PORT})"
elif bashio::services.available "mqtt" 2>/dev/null; then
    export MQTT_HOST=$(bashio::services mqtt "host")
    export MQTT_PORT=$(bashio::services mqtt "port")
    export MQTT_USER=$(bashio::services mqtt "username")
    export MQTT_PASS=$(bashio::services mqtt "password")
    bashio::log.info "MQTT credentials loaded from Supervisor service API (host=${MQTT_HOST}:${MQTT_PORT})"
else
    bashio::log.warning "MQTT credentials unavailable (all sources failed), using defaults"
    export MQTT_HOST="core-mosquitto"
    export MQTT_PORT="1883"
    export MQTT_USER=""
    export MQTT_PASS=""
fi
export MQTT_SSL=$(bashio::config 'mqtt.ssl' 'false')
export BOXES_JSON=$(bashio::config 'boxes' | jq -c .)
bashio::log.info "BOXES_JSON=${BOXES_JSON}"
export LOG_LEVEL=$(bashio::config 'system.log_level' 'INFO')

cd /opt/airsend
./bin/unix/${arch}/AirSendWebService 99399 &
LAUNCHER_PID=$!
bashio::log.info "AirSendWebService launcher started (PID: ${LAUNCHER_PID})"

bashio::log.info "Waiting for AirSendWebService on 127.0.0.1:33863..."
for i in $(seq 1 30); do
    if wget -q -O /dev/null "http://127.0.0.1:33863/service/status" 2>/dev/null; then
        bashio::log.info "AirSendWebService is up."
        break
    fi
    sleep 1
done

ASW_PID=""
for i in $(seq 1 10); do
    if [[ -f AirSendWebService.lock ]]; then
        ASW_PID="$(cat AirSendWebService.lock 2>/dev/null || true)"
        if [[ -n "$ASW_PID" ]]; then
            break
        fi
    fi
    sleep 1
done

if [[ -n "$ASW_PID" ]]; then
    bashio::log.info "AirSendWebService real PID (from lock file): ${ASW_PID}"
else
    bashio::log.warning "Could not read AirSendWebService.lock, falling back to launcher PID (may cause false-positive crash detection)"
    ASW_PID="$LAUNCHER_PID"
fi

(
    while kill -0 "$ASW_PID" 2>/dev/null; do
        sleep 10
    done
    bashio::log.error "AirSendWebService (PID: ${ASW_PID}) died, stopping addon..."
    kill -TERM 1
) &

cd /app
exec python3 main.py
