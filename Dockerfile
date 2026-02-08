# Używamy lekkiego obrazu Pythona
FROM python:3.11-slim

# Instalujemy podstawowe narzędzia systemowe
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# === NOWOŚĆ: Instalujemy "Standardowy Zestaw" bibliotek ===
# Dzięki temu Agent nie musi ich instalować ręcznie za każdym razem
RUN pip install --no-cache-dir matplotlib pandas numpy requests seaborn scikit-learn openpyxl

# Ustawiamy katalog roboczy
WORKDIR /workspace

# Domyślna komenda
CMD ["tail", "-f", "/dev/null"]