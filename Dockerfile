FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY templates /app/templates
COPY static /app/static

# Create directories if they don't exist
RUN mkdir -p /app/templates /app/static

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
