# NurseSync API image, pushed to Amazon ECR and run on the EC2 Auto Scaling Group.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# run as an unprivileged user
RUN useradd --create-home app
USER app

EXPOSE 8000
# behind the ALB and CloudFront: trust their X-Forwarded-* headers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
