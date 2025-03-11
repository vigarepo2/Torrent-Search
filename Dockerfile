FROM python:3.9-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask flask-cors

# Copy application code
COPY app.py .
COPY templates/ templates/

# Create static directory if it doesn't exist
RUN mkdir -p static

# Expose the port the app runs on
EXPOSE 5000

# Run the application with proper host binding for Docker
CMD ["python", "-u", "app.py"]
