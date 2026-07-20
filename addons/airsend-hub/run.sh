#!/usr/bin/with-contenv bashio
set -e

# --- Reprend fidelement la logique de detection d'archi de l'addon d'origine ---
# (mapping des noms d'archi apk vers les noms de dossier du tarball AirSendWebService)
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

# --- Config -> variables d'env consommees par main.py ---
export MQTT_HOST=$(bashio::services mqtt "host")
export MQTT_PORT=$(bashio::services mqtt "port")
export MQTT_USER=$(bashio::services mqtt "username")
export MQTT_PASS=$(bashio::services mqtt "password")
export MQTT_SSL=$(bashio::config 'mqtt.ssl' 'false')
export BOXES_JSON=$(bashio::config 'boxes' | jq -c .)
bashio::log.info "BOXES_JSON=${BOXES_JSON}"
export LOG_LEVEL=$(bashio::config 'system.log_level' 'INFO')

# --- Demarre AirSendWebService ---
# Invocation ("... 99399") reprise telle quelle de la branche "SUPERVISOR_TOKEN
# present" de l'addon d'origine. La signification exacte de l'argument n'est
# pas documentee mais l'invocation est celle empiriquement validee.
#
# IMPORTANT : le binaire SE DEMONISE LUI-MEME (fork + le process lanceur
# quitte immediatement). C'est confirme par le run.sh original, qui ne se
# fie JAMAIS au PID du "&" : il lit le vrai PID depuis un fichier
# "AirSendWebService.lock" ecrit par le binaire une fois demonise. Sans ca,
# on capte le PID du lanceur (qui meurt normalement des la demonisation
# terminee) et on croit a tort que le service a crashe alors qu'il tourne
# tres bien - c'est exactement ce qui se passait dans la version precedente
# de ce script (kill -0 sur le mauvais PID).
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

# --- Recupere le VRAI PID depuis le lock file (ecrit par le binaire une fois
# demonise), avec une petite marge d'attente au cas ou l'ecriture du lock
# survienne juste apres que /service/status reponde deja. ---
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

# --- Surveille AirSendWebService en fond. S'il meurt, on arrete tout le
# conteneur plutot que de laisser tourner l'app Python sans moteur RF
# fonctionnel - Supervisor redemarrera l'addon selon sa politique habituelle.
(
    while kill -0 "$ASW_PID" 2>/dev/null; do
        sleep 10
    done
    bashio::log.error "AirSendWebService (PID: ${ASW_PID}) died, stopping addon..."
    kill -TERM 1
) &

# --- Demarre l'app Python en foreground (devient le PID 1 logique du
# conteneur suite a l'exec ci-dessous ; le moniteur ci-dessus reste un
# processus enfant independant, non affecte par cet exec). ---
cd /app
exec python3 main.py
