# Spark 3.5.3 + PySpark, with the Kafka connector jars baked in so jobs
# start without downloading anything (works offline on demo day).
FROM apache/spark:3.5.3-python3

USER root

ARG MAVEN=https://repo1.maven.org/maven2
ADD --chmod=644 ${MAVEN}/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.3/spark-sql-kafka-0-10_2.12-3.5.3.jar /opt/spark/jars/
ADD --chmod=644 ${MAVEN}/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.3/spark-token-provider-kafka-0-10_2.12-3.5.3.jar /opt/spark/jars/
ADD --chmod=644 ${MAVEN}/org/apache/kafka/kafka-clients/3.4.1/kafka-clients-3.4.1.jar /opt/spark/jars/
ADD --chmod=644 ${MAVEN}/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar /opt/spark/jars/

# numpy is required by Spark MLlib (bonus prediction job)
RUN pip install --no-cache-dir numpy==1.24.4

RUN mkdir -p /opt/spark-apps /opt/data && chown -R spark:spark /opt/spark-apps /opt/data

USER spark
WORKDIR /opt/spark-apps
