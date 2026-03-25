FROM python:3-alpine

WORKDIR /app

COPY setup.py MANIFEST.in README.md LICENSE ./
COPY ldap_watchdog/ ./ldap_watchdog/

RUN pip install --no-cache-dir .[slack]

CMD ["ldap-watchdog"]
