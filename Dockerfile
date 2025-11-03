FROM python:3.10
COPY . /app
WORKDIR /app
RUN pip install python-dotenv notion-client colorama tqdm requests Pillow tenacity
CMD ["python", "magic-notion.py"]
