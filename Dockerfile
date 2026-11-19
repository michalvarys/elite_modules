# Odoo image s moduly Elite (elite_common, elite_vet, elite_arena, elite_trafika).
#
# Zaklad je Varyshop Odoo 18: zdrojaky Odoo lezi v /app a bezi pod rootem.
# Image stavi GitHub Actions (.github/workflows/docker-image.yml) a pushuje
# do ghcr.io/michalvarys/elite_modules. Lokalni vyvoj pouziva Dockerfile.dev.
ARG BASE_IMAGE=varyshop/website:release-1.1.0
FROM ${BASE_IMAGE}

# Python balicky navic (ted kvuli modulu mcp_server, ktery v gitu neni).
COPY requirements.txt /tmp/elite-requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/elite-requirements.txt \
    && rm /tmp/elite-requirements.txt

# Zakladni image nema prikaz `odoo`, se kterym pocita /entrypoint.sh
# i postupy v nasazeni/ (`odoo -d ... -u ...`, `odoo shell`).
RUN printf '#!/bin/sh\nexec python3 /app/odoo-bin "$@"\n' > /usr/local/bin/odoo \
    && chmod +x /usr/local/bin/odoo

# Moduly. Lokalne je prekryje volume ./:/mnt/modules z docker-compose.yml.
COPY elite_common /mnt/modules/elite_common
COPY elite_vet /mnt/modules/elite_vet
COPY elite_arena /mnt/modules/elite_arena
COPY elite_trafika /mnt/modules/elite_trafika

# Vychozi konfigurace, na serveru se obvykle prekryje vlastnim /etc/odoo.
COPY config/odoo-image.conf /etc/odoo/odoo.conf
ENV ODOO_RC=/etc/odoo/odoo.conf
RUN mkdir -p /var/lib/odoo

EXPOSE 8069 8072
CMD ["odoo"]
