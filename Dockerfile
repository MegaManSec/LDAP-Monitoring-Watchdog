FROM python:3-alpine

WORKDIR /app

COPY requirements.txt pyproject.toml setup.py MANIFEST.in README.md LICENSE ./
COPY ldap_watchdog/ ./ldap_watchdog/

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps .

CMD ["ldap-watchdog"]
