FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
RUN echo 'WEBVERSE{pl4st1c_dr34ms_m3lt_1n_th3_sun}' > /root/flag.txt
CMD ["python", "src/app.py"]
