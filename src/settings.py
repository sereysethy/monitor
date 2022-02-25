import configparser
import os 
from os.path import join

dir_path = os.path.dirname(os.path.realpath(__file__))
config_path = join(dir_path, 'config.ini')

config = configparser.ConfigParser()
config.read(config_path)

def getLoglevel():
    return config['log']['level']

def getTargetContainerName():
    return config['target_system']['container_name']

def getNetworkInterface():
    return config['target_system']['network_interface']

def getDockerURI():
    return config['docker']['uri']

def getRedisHost():
    return config['redis']['host']

def getRedisPort():
    return int(config['redis']['port'])

def getProcessChannel():
    return config['process_table']['channel']

def getProcessLoopingTime():
    return int(config['process_table']['looping_time'])

def getTerminateProcessChannel():
    return config['terminate_process']['channel']

def getTerminateProcessLoopingTime():
    return int(config['terminate_process']['looping_time'])

def getCPUMemMetricAvgLength():
    return int(config['metric']['metric_cpu_mem_avg_length'])

def getNetworkMetricAvgLength():
    return int(config['metric']['metric_network_avg_length'])
