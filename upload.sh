docker build -t needle:latest .
docker tag needle:latest **.**.cn/your_space/needle:latest
docker login -u ai -p your_pwd **.**.cn
docker push **.**.cn/your_space/needle:latest
