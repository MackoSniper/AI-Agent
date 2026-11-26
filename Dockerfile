# Use a lightweight Python image
FROM python:3.11-slim

# Install basic system tools
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# === NEW: Install a "standard set" of libraries ===
# This way the agent doesn't have to install them manually every time
RUN pip install --no-cache-dir matplotlib pandas numpy requests seaborn scikit-learn openpyxl

# Set the working directory
WORKDIR /workspace

# Default command
CMD ["tail", "-f", "/dev/null"]