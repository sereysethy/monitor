import configparser
import os 
from os.path import join

dir_path = os.path.dirname(os.path.realpath(__file__))
config_path = join(dir_path, 'config.ini')

config = configparser.ConfigParser()
config.read(config_path)

def getLoglevel():
    return config.get('log', 'level', fallback="INFO")

def getLogpath():
    return config.get('log', 'path', fallback="/usr/monitor/log")

def getTargetContainerName():
    return config.get('target_system', 'container_name')

def getNetworkInterface():
    return config.get('target_system', 'network_interface')

def getDockerURI():
    return config.get('docker', 'uri')

def getRedisHost():
    return config.get('redis', 'host', fallback='localhost')

def getRedisPort():
    return config.getint('redis', 'port', fallback=6379)

def getProcessChannel():
    return config.get('process', 'channel')

def getProcessLoopingTime():
    return config.getint('process', 'looping_time')

def getCPUMemMetricAvgLength():
    return config.getint('metric', 'metric_cpu_mem_avg_length')

def getNetworkMetricAvgLength():
    return config.getint('metric', 'metric_network_avg_length')

