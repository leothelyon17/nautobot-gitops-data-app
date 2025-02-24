FROM python:3.11-slim

# Set the working directory.
WORKDIR /app

# Copy and install Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Streamlit app code.
COPY app.py .

# Expose the default Streamlit port.
EXPOSE 8501

# Run the Streamlit app.
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
