FROM python:3.9-slim

WORKDIR /app

# Create directories
RUN mkdir -p /app/templates

# Copy application files
COPY app.py .
COPY requirements.txt .
COPY templates/index.html ./templates/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
