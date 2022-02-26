import redis
import os
import logging
import configparser
import time
import signal
from os.path import join
import sys
from logging.handlers import TimedRotatingFileHandler

# global
global_running = True

def handler(signum, stack):
    global global_running
    if signum == signal.SIGTERM:
        global_running = False

def runTerminateProcessLoop(channel, loopingTime):
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

    global global_running

    while global_running:
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
        time.sleep(loopingTime)

# redis
def getRedisClient(config):
    try:
        host = config.get('redis', 'host', fallback='localhost')
        port = config.getint('redis', 'port', fallback=6379)
        redisClient = redis.Redis(host=host, port=port)
    except redis.ConnectionError:
        exit(1)
    
    return redisClient

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handler)
    if len(sys.argv) < 2:
        sys.exit(1)

    configPath = sys.argv[1]
    config = configparser.ConfigParser()
    config.read(configPath)
    
    logLevel = config.get('log', 'level', fallback='INFO')
    logPath = config.get('log', 'path')
    logPathname = join(logPath, 'terminate.log')
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logLevel, 
        handlers=[
            TimedRotatingFileHandler(logPathname, when='midnight'),
            logging.StreamHandler()
        ])

    channelName = config.get('terminate', 'channel_name')
    loopingTime = config.getint('terminate', 'looping_time')

    logging.info('REDIS_TERMINATE_CHANNEL_NAME: %s', channelName)
    logging.info('TERMINATE_LOOPING_TIME: %s', loopingTime)

    redisClient = getRedisClient(config)
    channel = redisClient.pubsub()
    channel.subscribe(channelName)
    logging.info('subscribing to the Redis channel: %s', channelName)

    logging.info("start the terminating process loop")
    runTerminateProcessLoop(channel, loopingTime)

    