FROM python:3.9-slim

WORKDIR /app

# Create directories first
RUN mkdir -p /app/templates /app/static

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY templates/* /app/templates/

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
