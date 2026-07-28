FROM python:3.11-slim
WORKDIR /app

# System deps for numpy/sklearn (no GPU)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Radlex ontology — expected at /app/data/Radlex.xls
# To mount externally: docker run -v /path/to/Radlex.xls:/app/data/Radlex.xls ...
# Or override the path: -e RADLEX_PATH=/custom/path/Radlex.xls
ENV RADLEX_PATH=/app/data/Radlex.xls

EXPOSE 5003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5003"]
