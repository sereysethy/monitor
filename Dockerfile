FROM python:3.8

WORKDIR /usr/src/app
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY src /usr/src/app
COPY terminate /usr/terminate

# CMD ["python", "metric.py"]