import logging
import time
import numpy as np
import docker
from logging.handlers import TimedRotatingFileHandler
from os.path import join
from settings import getLoglevel, getLogpath

logpath = join(getLogpath(), 'metric.log')
loglevel = getLoglevel()
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=loglevel,
                    handlers=[
                        TimedRotatingFileHandler(logpath, when='midnight'),
                        logging.StreamHandler()
                    ])

from settings import getTargetContainerName, getNetworkInterface
from settings import getCPUMemMetricAvgLength, getNetworkMetricAvgLength

from utils import getRedisClient, getDockerClient

keys = [
    'list_cpu_usage_per',
    'list_mem_usage_per',
    'list_net_in_byte',
    'list_net_out_byte',
    'avg_net_flow_in_byte',
    'avg_net_flow_out_byte',
    'cpu_usage_per',
    'mem_usage_per',
    'net_in_byte',
    'mem_out_byte',
]

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
        blkReadByte, blkWriteByte = _getBlkIOfromMetric(metric)

        # push the current metric to the redis lists
        redisClient.lpush('list_cpu_usage_per', cpuUsagePercent)
        redisClient.lpush('list_mem_usage_per', memUsagePercent)
        redisClient.lpush('list_net_in_byte', netInUsageByte)
        redisClient.lpush('list_net_out_byte', netOutUsageByte)

        # set the current metric to the redis
        redisClient.set('cpu_usage_per', cpuUsagePercent)
        redisClient.set('mem_usage_per', memUsagePercent)
        redisClient.set('net_in_byte', netInUsageByte)
        redisClient.set('net_out_byte', netOutUsageByte)
        redisClient.set('blk_read_byte', blkReadByte)
        redisClient.set('blk_write_byte', blkWriteByte)

        calculateAvgCpuAndMem()
        calAvgNetworkFlow()

def _getBlkIOfromMetric(metric):
    """
    This will sum all the i/o read and write operations.

    Params
    ------
        metric (dict): stats containing the metric of a container
    Returns
    -------
        read_bytes (int) and write_bytes (int)
    """

    io_stats = metric['blkio_stats']['io_service_bytes_recursive']

    read_bytes = 0
    write_bytes = 0

    for entry in io_stats:
        if entry['op'] == 'Read':
            read_bytes += entry['value']
        elif entry['op'] == 'Write':
            write_bytes += entry['value']

    return read_bytes, write_bytes

def calculateAvgCpuAndMem():
    """
    The idea is to caculate an average over n of cpu and memory comsumption metrics.

    How to define n? For now we can fix it to the last 5 or 10?
    """

    # get the first values equal to CPU_MEM_METRIC_LENGTH
    cpus = redisClient.lrange('list_cpu_usage_per', 0, CPU_MEM_METRIC_LENGTH)
    mems = redisClient.lrange('list_mem_usage_per', 0, CPU_MEM_METRIC_LENGTH)

    listCpus = []
    for cpu in cpus:
        listCpus.append(float(cpu))

    listMem = []
    for mem in mems:
        listMem.append(float(mem))

    if listCpus:
        avgCpuUsagePercent = np.average(listCpus).tolist()
    else:
        avgCpuUsagePercent = 0.0
    if listMem:
        avgMemUsagePercent = np.average(listMem).tolist()
    else:
        avgMemUsagePercent = 0.0

    # write the averaged values to Redis
    redisClient.set('avg_cpu_usage_per', avgCpuUsagePercent)
    redisClient.set('avg_mem_usage_per', avgMemUsagePercent)

    # maintain a last CPU_MEM_METRIC_LENGTH values in the Redis list
    redisClient.ltrim('list_cpu_usage_per', 0, CPU_MEM_METRIC_LENGTH + 1)
    redisClient.ltrim('list_mem_usage_per', 0, CPU_MEM_METRIC_LENGTH + 1)

def calAvgNetworkFlow():
    """
    This function will calculate the differnce between each networks in/out
    bytes written and then average them.

    It indicates the flow of data in and out per a window of NETWORK_METRIC_LENGTH
    """

    # get the first values equal to CPU_MEM_METRIC_LENGTH
    netIns = redisClient.lrange('list_net_in_byte', 0, NETWORK_METRIC_LENGTH)
    netOuts = redisClient.lrange('list_net_out_byte', 0, NETWORK_METRIC_LENGTH)

    listNetIn = []
    for netin in netIns:
        listNetIn.append(float(netin))

    listNetOut = []
    for netout in netOuts:
        listNetIn.append(float(netout))

    # calculate the difference of each value
    avgNetFlowIn = np.average(np.diff(listNetIn))
    avgNetFlowOut = np.average(np.diff(listNetOut))

    # write the averaged flow to Redis
    redisClient.set('avg_net_flow_in_byte', avgNetFlowIn)
    redisClient.set('avg_net_flow_out_byte', avgNetFlowOut)

    # maintain a last CPU_MEM_METRIC_LENGTH values in the Redis list
    redisClient.ltrim('list_net_in_byte', 0, NETWORK_METRIC_LENGTH + 1)
    redisClient.ltrim('list_net_out_byte', 0, NETWORK_METRIC_LENGTH + 1)

def clearRedisKeys():
    """
    When the program starts, this function should be called if we use a persistent
    Redis or a Redis on a host: because data are preserved.
    """

    logging.info('Clear all Redis keys')
    for key in keys:
        logging.info('Delete key: %s', key)
        redisClient.delete(key)

if __name__ == "__main__":

    # clearRedisKeys()

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
