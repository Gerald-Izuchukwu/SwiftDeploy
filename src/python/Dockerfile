FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt /app

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app

RUN addgroup --gid 1000 devgroup && adduser --uid 1000 --gid 1000 --home /app dev && chown -R dev:devgroup /app

USER dev
ENV MODE=stable 
ENV PORT=3000 
ENV VERSION=1.0

EXPOSE 5000

CMD ["python", "app.py"]