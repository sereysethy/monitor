import logging
import time
import numpy as np
import docker
from logging.handlers import TimedRotatingFileHandler

from settings import getLoglevel
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=getLoglevel(), 
                    handlers=[
                        TimedRotatingFileHandler("logs/metric.log", when='midnight'),
                        logging.StreamHandler()
                    ])

from settings import getTargetContainerName, getNetworkInterface
from settings import getCPUMemMetricAvgLength, getNetworkMetricAvgLength

from utils import getRedisClient, getDockerClient

# get docker client
dockerClient = getDockerClient()

# redis
redisClient = getRedisClient()

# metric, constant from the configuration file
CPU_MEM_METRIC_LENGTH = getCPUMemMetricAvgLength()
NETWORK_METRIC_LENGTH = getNetworkMetricAvgLength()
logging.info('CPU_MEM_METRIC_LENGTH: %d', CPU_MEM_METRIC_LENGTH)
logging.info('NETWORK_METRIC_LENGTH: %d', NETWORK_METRIC_LENGTH)

def runMetricsLoop(container, networkInterface):
    """
    This function will fetch stream of metric data from the docker container.

    At each iteration, it will gather a metric information and store them in 
    a redis server for later consumption. The metric inforamtion is updated
    continuosly.

    Type of data stored in the redis server:

        Data
        ----
            cpu_usage (percentage):
            mem_usage (percentage):
            netInUsage (int): number of network traffic received in bytes
            netOutUsage (int): number of network traffic transmitted in bytes

        Params
        ------
            container (docker.Container) container object that we want to gather
            its metric.
        Returns
        ------
            It does not return any values.
    """

    for metric in container.stats(decode=True):
        logging.debug('getting metric: %s', metric)
        cpuUsagePercent = 0.0
        # calculate the change for the cpu usage of the container in between readings
        cpuDelta = metric["cpu_stats"]["cpu_usage"]["total_usage"] - metric["precpu_stats"]["cpu_usage"]["total_usage"]

        # calculate the change for the entire system between readings
        if "system_cpu_usage" in metric["precpu_stats"]:
            systemDelta = metric["cpu_stats"]["system_cpu_usage"] - metric["precpu_stats"]["system_cpu_usage"]
        else:
            systemDelta = 0

        if systemDelta > 0 and cpuDelta > 0:
            cpuUsagePercent = (cpuDelta / systemDelta) * metric["cpu_stats"]["online_cpus"] * 100.0
        else:
            cpuUsagePercent = 0.0
        
        # get a current read
        memUsagePercent = metric['memory_stats']['usage'] * 100/metric['memory_stats']['limit']
        netInUsageByte = metric['networks'][networkInterface]['rx_bytes']
        netOutUsageByte = metric['networks'][networkInterface]['tx_bytes']

        # push the current metric to the redis lists
        redisClient.lpush('list_cpu_usage_per', cpuUsagePercent)
        redisClient.lpush('list_mem_usage_per', memUsagePercent)
        redisClient.lpush('list_net_in_byte', netInUsageByte)
        redisClient.lpush('list_mem_out_byte', netOutUsageByte)

        # set the current metric to the redis
        redisClient.set('cpu_usage_per', cpuUsagePercent)
        redisClient.set('mem_usage_per', memUsagePercent)
        redisClient.set('net_in_byte', netInUsageByte)
        redisClient.set('mem_out_byte', netOutUsageByte)

        calculateAvgCpuAndMem()
        calAvgNetworkFlow()
        
def calculateAvgCpuAndMem():
    """
    The idea is to caculate an average over n of cpu and memory comsumption metrics.

    How to define n? For now we can fix it to the last 5 or 10?
    """

    # write them to redis
    cpus = redisClient.lrange('list_cpu_usage_per', 0, CPU_MEM_METRIC_LENGTH)
    mems = redisClient.lrange('list_mem_usage_per', 0, CPU_MEM_METRIC_LENGTH)

    listCpus = []
    for cpu in cpus:
        listCpus.append(float(cpu))

    listMem = []
    for mem in mems:
        listMem.append(float(mem))

    avgCpuUsagePercent = np.average(listCpus)
    avgMemUsagePercent = np.average(listMem)

    redisClient.set('avg_cpu_usage_per', avgCpuUsagePercent)
    redisClient.set('avg_mem_usage_per', avgMemUsagePercent)

def calAvgNetworkFlow():
    """
    This function will calculate the differnce between each networks in/out
    bytes written and then average them.

    """

    # write them to redis
    netIns = redisClient.lrange('list_net_in_byte', 0, NETWORK_METRIC_LENGTH)
    netOuts = redisClient.lrange('list_net_out_byte', 0, NETWORK_METRIC_LENGTH)

    listNetIn = []
    for netin in netIns:
        listNetIn.append(float(netin))

    listNetOut = []
    for netout in netOuts:
        listNetIn.append(float(netout))

    avgNetFlowIn = np.average(np.diff(listNetIn))
    avgNetFlowOut = np.average(np.diff(listNetOut))

    redisClient.set('avg_net_flow_in_byte', avgNetFlowIn)
    redisClient.set('avg_net_flow_out_byte', avgNetFlowOut)

if __name__ == "__main__":

    # connect to the running target system
    targetName = getTargetContainerName()
    networkInterface = getNetworkInterface()
    while True:
        try:
            container = dockerClient.containers.get(targetName)
            if container:
                break
        except docker.errors.NotFound as e:
            logging.error("%s", e)
            time.sleep(5)

    logging.info("starting the metric loop")
    runMetricsLoop(container, networkInterface)

