import sys
import hashlib
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

def getFileHash(path: str, hashalgo: str = "sha256")->str:
    """
    This will return a hash of a file.

    Params
    ------
        path (str): path to file to find hash
        hashalgo (str): hash algorithm, default is sha256
    Returns
    -------
        hash of the file or None if file not found
    """

    m = hashlib.new(hashalgo)
    digest = None

    try:
        with open(path, 'rb') as fin:
            m.update(fin.read())
            digest = m.hexdigest()
    except FileNotFoundError as e:
        logging.info(f"{e}")
        digest = None
    except PermissionError as e:
        logging.info(f"{e}")
        digest = None

    return digest
