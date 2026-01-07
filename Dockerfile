FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Instala as dependências incluindo a nova biblioteca de disfarce
RUN pip install --no-cache-dir fastapi uvicorn playwright pydantic playwright-stealth

# Instala o navegador Chromium
RUN playwright install chromium

COPY . .

# Expondo a porta 80 conforme configurado no Easypanel
EXPOSE 80

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
