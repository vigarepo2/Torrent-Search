FROM python:3.9-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask flask-cors

# Copy application code
COPY app.py .
COPY templates/ templates/

# Expose the port the app runs on
EXPOSE 5000

# Command to run the app with the correct host binding
CMD ["python", "-c", "import app; app.app.run(debug=True, host='0.0.0.0', port=5000)"]
