FROM python:3.12-slim
WORKDIR /srv
COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt
COPY backend /srv/backend
COPY frontend /srv/frontend
COPY data /srv/data
WORKDIR /srv/backend
ENV HIDRO_DATA=/srv/data HIDRO_FRONTEND=/srv/frontend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
