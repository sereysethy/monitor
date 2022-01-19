import configparser
import os 
from os.path import join

dir_path = os.path.dirname(os.path.realpath(__file__))
config_path = join(dir_path, 'config.ini')

config = configparser.ConfigParser()
config.read(config_path)

def getTargetContainerName():
    return config['target_system']['container_name']

def getNetworkInterface():
    return config['target_system']['network_interface']

def getDockerURI():
    return config['docker']['uri']

def getRedisHost():
    return config['redis']['host']

def getRedisPort():
    return config['redis']['port']