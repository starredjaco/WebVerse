FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV CONFIG_PATH /srv/orbitdesk/config

RUN mkdir /srv/orbitdesk/
RUN mkdir /srv/orbitdesk/config/

COPY service.env /srv/orbitdesk/config/

RUN mkdir /data/
RUN mkdir /data/storage/

COPY env /data/storage/.env
COPY env /data/storage/env

EXPOSE 8000
CMD ["python","app.py"]
