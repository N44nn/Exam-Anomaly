#!/bin/bash
# One-time HDFS setup for Ubuntu/WSL
set -e
sudo apt-get update -qq
sudo apt-get install -y openjdk-11-jdk openssh-server wget > /dev/null

export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
[ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -P "" -f ~/.ssh/id_rsa
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
sudo service ssh start

cd ~
if [ ! -d hadoop ]; then
  wget -nc https://archive.apache.org/dist/hadoop/common/hadoop-3.3.6/hadoop-3.3.6.tar.gz
  tar -xzf hadoop-3.3.6.tar.gz && mv hadoop-3.3.6 hadoop
fi

grep -q HADOOP_HOME ~/.bashrc || cat >> ~/.bashrc <<'EOT'
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export HADOOP_HOME=$HOME/hadoop
export PATH=$PATH:$HADOOP_HOME/bin:$HADOOP_HOME/sbin
EOT
export HADOOP_HOME=$HOME/hadoop
export PATH=$PATH:$HADOOP_HOME/bin:$HADOOP_HOME/sbin
echo "export JAVA_HOME=$JAVA_HOME" >> $HADOOP_HOME/etc/hadoop/hadoop-env.sh

cat > $HADOOP_HOME/etc/hadoop/core-site.xml <<'EOT'
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:9000</value></property>
</configuration>
EOT
cat > $HADOOP_HOME/etc/hadoop/hdfs-site.xml <<EOT
<configuration>
  <property><name>dfs.replication</name><value>1</value></property>
  <property><name>dfs.namenode.name.dir</name><value>file:///home/$USER/hdfs/namenode</value></property>
  <property><name>dfs.datanode.data.dir</name><value>file:///home/$USER/hdfs/datanode</value></property>
</configuration>
EOT
mkdir -p ~/hdfs/namenode ~/hdfs/datanode
[ -d ~/hdfs/namenode/current ] || hdfs namenode -format -force
start-dfs.sh
hdfs dfs -mkdir -p /exam
echo "HDFS ready. Check: hdfs dfs -ls /"
