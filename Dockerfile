FROM python:3.8

WORKDIR /usr/monitor
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY monitor /usr/monitor
COPY terminate /usr/terminate

# CMD ["python", "metric.py"]