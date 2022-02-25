import logging
import time
import os
import signal

from settings import getLoglevel
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=getLoglevel(), 
                    handlers=[
                        logging.FileHandler("logs/terminate.log"),
                        logging.StreamHandler()
                    ])

from settings import getTerminateProcessChannel, getTerminateProcessLoopingTime
from utils import getRedisClient

# metric, constant from the configuration file
REDIS_TERMINATE_CHANNEL_NAME = getTerminateProcessChannel()
TERMINATE_LOOPING_TIME = getTerminateProcessLoopingTime()
logging.info('REDIS_TERMINATE_CHANNEL_NAME: %s', REDIS_TERMINATE_CHANNEL_NAME)
logging.info('TERMINATE_LOOPING_TIME: %s', TERMINATE_LOOPING_TIME)

redisClient = getRedisClient()
channel = redisClient.pubsub()
res = channel.subscribe(REDIS_TERMINATE_CHANNEL_NAME)
logging.info('subscribing to the Redis channel: %s', REDIS_TERMINATE_CHANNEL_NAME)

def runTerminateProcessLoop():

    """
    This function will fetch pid of a running process from a redis channel and
    terminate it by sending a SIGKILL signal.

    Pre-condition
    -------------
        There is a process to terminate identified by its PID

    Post-condition
    --------------
        The process is terminated.

    Params
    ------
        None
    Returns
    ------
        None
    """

    while True:
        message = channel.get_message()
        if message and message['type'] == 'message':
            pid = int(message['data'])
            try:
                logging.debug("sending SIGKILL to the process pid: %d", pid)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError as e:
                logging.error(e)
            except PermissionError as e:
                logging.error(e)
        time.sleep(TERMINATE_LOOPING_TIME)

    
if __name__ == "__main__":
    logging.info("start the terminating process loop")
    runTerminateProcessLoop()