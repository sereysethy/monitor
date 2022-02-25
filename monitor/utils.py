import sys
import docker
import redis
from settings import getRedisHost, getRedisPort, getDockerURI
import logging

# redis
def getRedisClient():
    redisHost = getRedisHost()
    redisPort = getRedisPort()
    redisClient = redis.Redis(host=redisHost, port=redisPort)
    if redisClient:
        logging.info("connecting to a redis server %s on port %d",
                        redisHost, redisPort)
    else:
        logging.critical("failed to connect to a redis server %s on port %d: ",
                        redisHost, redisPort)
        sys.exit(1)
    return redisClient

def getDockerClient():
    # get docker client
    socketPath = getDockerURI()
    logging.info("getting docker socket from a host server: %s", socketPath)
    dockerClient = docker.DockerClient(base_url=socketPath)
    return dockerClient