FROM registry.sberdevices.ru/rndml/devops/dockerfiles/python:3.12-bullseye

ENV PIP_INDEX_URL=https://nexus.sberdevices.ru/repository/Pypi/simple

COPY ./requirements.txt /tmp/requirements.txt

RUN pip install --index-url $PIP_INDEX_URL --no-cache-dir --upgrade pip && \
    pip install --index-url $PIP_INDEX_URL --no-cache-dir --upgrade wheel setuptools && \  
    pip install --index-url $PIP_INDEX_URL --no-cache-dir -r /tmp/requirements.txt 


COPY ./app/ /app/

WORKDIR /app

ENV PYTHONPATH="."

CMD python3 -u run.py