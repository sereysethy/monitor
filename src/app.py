import logging
import sys
import docker
import redis

from os.path import isfile, join

import json
import re

from datetime import datetime, timedelta

from settings import getDockerURI, getRedisHost, getRedisPort, getTargetContainerName, getNetworkInterface

# configure logging
logging.getLogger().setLevel(logging.DEBUG)

# get docker client
logging.info("Getting docker socket from a host server")
socketPath = getDockerURI()
dockerClient = docker.DockerClient(base_url=socketPath)

# redis
logging.info("Connecting to a redis server")
redisHost = getRedisHost()
redisPort = getRedisPort()

redisClient = redis.Redis(
    host=redisHost,
    port=redisPort)

def runMetricsLoop(container, networkInterface):
    """
    This function will fetch stream of metric data from the docker container.

    At each iteration, it will gather a metric information and store them in 
    a redis server for later consumption. The metric inforamtions are updated
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
        cpuPercent = 0.0
        # calculate the change for the cpu usage of the container in between readings
        cpuDelta = metric["cpu_stats"]["cpu_usage"]["total_usage"] - metric["precpu_stats"]["cpu_usage"]["total_usage"]

        # calculate the change for the entire system between readings
        if "system_cpu_usage" in metric["precpu_stats"]:
            systemDelta = metric["cpu_stats"]["system_cpu_usage"] - metric["precpu_stats"]["system_cpu_usage"]
        else:
            systemDelta = 0

        if systemDelta > 0 and cpuDelta > 0:
            cpuPercent = (cpuDelta / systemDelta) * metric["cpu_stats"]["online_cpus"] * 100.0
            
            redisClient.set('cpu_usage', cpuPercent)
        else:
            redisClient.set('cpu_usage', 0.0)
        
        memUsage = metric['memory_stats']['usage'] * 100/metric['memory_stats']['limit']
        netInUsage = metric['networks'][networkInterface]['rx_bytes']
        netOutUsage = metric['networks'][networkInterface]['tx_bytes']
        
        redisClient.set('mem_usage', memUsage)
        redisClient.set('net_in', netInUsage)
        redisClient.set('net_out', netOutUsage)

if __name__ == "__main__":

    # connect to the running target system
    targetName = getTargetContainerName()
    container = dockerClient.containers.get(targetName)
    networkInterface = getNetworkInterface()

    logging.info("Start the metric loop")
    runMetricsLoop(container, networkInterface)