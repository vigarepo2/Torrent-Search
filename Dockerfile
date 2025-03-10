FROM python:3.9-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask flask-cors

# Copy application code
COPY app.py .
COPY templates/ templates/

# Expose the port the app runs on
EXPOSE 5000

# Simple and direct command to run the app with proper host binding
CMD ["python", "app.py"]
