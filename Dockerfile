# Use Python 3.9 slim image as base - smaller footprint than full Python
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask flask-cors

# Copy application code
COPY app.py .
COPY templates/ templates/

# Create a non-root user for security
RUN groupadd -r app && useradd -r -g app app

# Change ownership of the application files
RUN chown -R app:app /app

# Switch to non-root user
USER app

# Expose the port the app runs on
EXPOSE 80

# Command to run the application
CMD ["python", "app.py"]
