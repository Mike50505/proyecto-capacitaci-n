FROM python:3.13-slim
WORKDIR /app
COPY server.py ./
COPY static ./static
COPY data ./data
COPY assets/figures ./assets/figures
RUN useradd --create-home training && mkdir -p private assets/uploads && chown -R training:training /app
USER training
EXPOSE 55290
CMD ["python", "-u", "server.py", "--host", "0.0.0.0", "--port", "55290"]
