FROM python:3.10.14

RUN mkdir -p /home/needle

COPY requirements.txt /home/needle

WORKDIR /home/needle

RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

COPY . /home/needle

CMD ["python", "main.py"]
