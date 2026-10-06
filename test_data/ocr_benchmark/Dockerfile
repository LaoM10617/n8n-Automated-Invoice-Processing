FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir paddleocr==3.7.0 paddlepaddle==3.2.2
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
WORKDIR /probe
