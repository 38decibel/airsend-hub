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

export MQTT_HOST=$(bashio::services mqtt "host")
export MQTT_PORT=$(bashio::services mqtt "port")
export MQTT_USER=$(bashio::services mqtt "username")
export MQTT_PASS=$(bashio::services mqtt "password")
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
