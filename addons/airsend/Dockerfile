ARG BUILD_FROM
FROM $BUILD_FROM

# Python runtime + outils necessaires au telechargement du binaire AirSendWebService.
# Vendorise le binaire officiel AirSendWebService (moteur RF local, cf. Phase 1)
# Ecoute en HTTP simple sur le port 33863 (confirme empiriquement, cf. discussion Phase 1 -
# NE PAS remettre de nginx/SSL devant, ce n'est pas necessaire malgre un vieux nginx.conf trouve
# dans l'ancien addon qui semble obsolete).
# chmod 777 (pas 755) : repris tel quel de l'addon d'origine - plusieurs
# binaires par architecture sous bin/unix/<arch>/, pas confirme lequel a
# strictement besoin de quels bits, on reproduit l'existant qui fonctionne.
RUN apk add --no-cache python3 py3-pip wget tar jq \
    && mkdir -p /opt/airsend && cd /opt/airsend && \
    wget http://devmel.com/dl/AirSendWebService.tgz && \
    tar -zxvf AirSendWebService.tgz && \
    rm AirSendWebService.tgz && \
    chmod -R 777 bin

# Dependances Python.
# aiohttp n'a plus de wheel precompile pour i386 (32 bits) depuis des annees
# (arret cote projet aiohttp) - contrairement a amd64/aarch64/armhf/armv7 qui
# ont bien un wheel pret pour la version Python de cette image. On installe
# donc une chaine de compilation C en "virtual package" le temps du pip
# install (sert de fallback source-build sur i386 uniquement), puis on la
# retire pour ne pas alourdir l'image finale sur les autres architectures.
COPY rootfs/app/requirements.txt /app/requirements.txt
RUN apk add --no-cache --virtual .build-deps gcc musl-dev python3-dev libffi-dev \
    && pip install --no-cache-dir --break-system-packages -r /app/requirements.txt \
    && apk del .build-deps

COPY rootfs/app /app
COPY run.sh /
RUN chmod a+x /run.sh

EXPOSE 33863

CMD [ "/run.sh" ]
