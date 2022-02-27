import logging
import time
import json
import docker
from os.path import join
from logging.handlers import TimedRotatingFileHandler
from settings import getLoglevel, getLogpath

logpath = join(getLogpath(), 'process.log')
loglevel = getLoglevel()
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=loglevel, 
                    handlers=[
                        TimedRotatingFileHandler(logpath, when='midnight'),
                        logging.StreamHandler()
                    ])

from settings import getTargetContainerName, getProcessLoopingTime, getProcessChannel
from utils import getRedisClient, getDockerClient

# get docker client
dockerClient = getDockerClient()

# redis
redisClient = getRedisClient()

# read from configuration setting
REDIS_CHANNEL_NAME = getProcessChannel()
LOOPING_TIME = getProcessLoopingTime()
logging.info('REDIS_CHANNEL_NAME: %s', REDIS_CHANNEL_NAME)
logging.info('LOOPING_TIME: %d', LOOPING_TIME)

def runProcessLoop(container):
    """
    This function will continously exect `docker top` on the container that
    we want to monitor. The docker top command will return the processes running
    inside the docker from a host perspective:

    UID     PID     PPID    C   STIME TTY TIME      CMD
    root    37209   37160   0   14:46 ?   00:00:00  /usr/sbin/sshd -D -e -o LogLevel=DEBUG3

    The function will then publish this to a redis channel so that the other
    the honeypot proxy will use them to make the decision.

    Params
    ------
        container (docker.Container) container object that we want to gather the
        information about the running processes.

    Returns
    ------
        None
    """

    while True:
        res = container.top()

        for proc in res['Processes']:
            logging.debug('processing process: %s', proc)
            puid = proc[0]
            pid = proc[1]
            ppid = proc[2]
            pstatus = proc[3]
            pstime = proc[4]
            ptty = proc[5]
            ptime = proc[6]
            pcmd = proc[7]
            
            o = {}
            o['uid'] = puid
            o['pid'] = pid
            o['ppid'] = ppid
            o['status'] = pstatus
            o['stime'] = pstime
            o['tty'] = ptty
            o['ptime'] = ptime
            o['cmd'] = pcmd
            
            redisClient.publish(REDIS_CHANNEL_NAME, json.dumps(o))

        time.sleep(LOOPING_TIME)

if __name__ == "__main__":
    # connect to the running target system
    targetName = getTargetContainerName()
    while True:
        try:
            container = dockerClient.containers.get(targetName)
            if container:
                break
        except docker.errors.NotFound as e:
            logging.error("%s", e)
            time.sleep(5)

    logging.info("starting the process monitor loop")
    runProcessLoop(container)

