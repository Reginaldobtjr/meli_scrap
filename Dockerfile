FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Instalação explícita das bibliotecas
RUN pip install --no-cache-dir fastapi uvicorn playwright pydantic playwright-stealth

# Instala o Chromium com as dependências do sistema
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 80

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
