import logging
import time
import json
import shutil
import docker
from os import path
import sys
from logging.handlers import TimedRotatingFileHandler

from settings import (
    getLoglevel,
    getLogpath,
    getTargetContainerName,
    getProcessLoopingTime,
    getProcessChannel,
    getProcPath,
    getDigestFile,
    getExeDirPath,
    getCmdDigestFile
)

from utils import getRedisClient, getDockerClient, getFileHash

logpath = path.join(getLogpath(), 'process.log')
loglevel = getLoglevel()
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=loglevel,
                    handlers=[
                        TimedRotatingFileHandler(logpath, when='midnight'),
                        logging.StreamHandler()
                    ])

# get docker client
dockerClient = getDockerClient()

# redis
redisClient = getRedisClient()

# this hold digests that we will be ignored
digestDict = {}

# this hold digests of commands that will not be saved
cmdDigestDict = {}

# this is flag to publish to redis or not
publish_to_redis = True

# read from configuration setting
REDIS_SSH_PROCESS = "ssh_process"
REDIS_CHANNEL_NAME = getProcessChannel()
PROC_PATH = getProcPath()
DIGEST_FILE = getDigestFile()
CMD_DIGEST_FILE = getCmdDigestFile()
EXE_DIR_PATH = getExeDirPath()
LOOPING_TIME = getProcessLoopingTime()
logging.info('REDIS_CHANNEL_NAME: %s', REDIS_CHANNEL_NAME)
logging.info('LOOPING_TIME: %d', LOOPING_TIME)

SSHD_PID = None

def loadCmdDigest()->dict:
    """
    Load command and their digests, these commands will not be saved!
    """

    global CMD_DIGEST_FILE

    cmdDict = {}

    logging.info(f"loading non-saved digest file at: {CMD_DIGEST_FILE}")

    with open(CMD_DIGEST_FILE, "r") as fin:
        for line in fin:
            cmdDigests = line.strip().split(":")
            cmd, digest = cmdDigests[0], cmdDigests[1]
            logging.debug(f"for cmd {cmd}, digest: {digest}")
            cmdDict[digest] = cmd

    return cmdDict

def loadDigest()->dict:
    """
    Load command and their digests, these commands will be ignored!
    """
    global DIGEST_FILE

    cmdDict = {}

    logging.info(f"loading digest file at: {DIGEST_FILE}")

    with open(DIGEST_FILE, "r") as fin:
        for line in fin:
            cmdDigests = line.strip().split(":")
            cmd, digest = cmdDigests[0], cmdDigests[1]
            logging.debug(f"for cmd {cmd}, digest: {digest}")
            cmdDict[digest] = cmd

    return cmdDict

def saveFile(filepath: str, name: str, digest: str)->None:
    """
    Save exe file, when they are not in the list
    """
    global EXE_DIR_PATH

    filename = f"{EXE_DIR_PATH}/filename.txt"
    dest = f"{EXE_DIR_PATH}/{digest}"
    if not path.isfile(dest):
        with open(filename, "a") as fout:
            logging.info(f"saving file {filename}, digest: {digest}")
            fout.write(f"{name}:{digest}\n")
            shutil.copy2(filepath, dest)

def isKnownHash(name: str, pid: str)->bool:
    """
    This will check exe corresponding to the pid in proc against a list of
    known files like /usr/sbin/sshd, /bin/bash, etc. and it will return `True`
    if its signature is known.

    Params
    ------
        pid (str): pid of exe to check
    Returns
    -------
        True if the hash is known in the list, otherwise False.
    """

    global PROC_PATH
    global digestDict, cmdDigestDict

    filepath = f"{PROC_PATH}/{pid}/exe"

    digest = getFileHash(filepath)

    if digest and digest in digestDict:
        return True
    else:
        if digest not in cmdDigestDict:
            saveFile(filepath, name, digest)
        else:
            logging.info(f"{name} is found, not saved!")
        return False

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

    global SSHD_PID
    global publish_to_redis

    logging.info("starting the process monitor loop")

    while True:
        res = container.top(ps_args="-eo uid,pid,ppid,c,stime,tty,time,cmd,comm")

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
            pcomm = proc[8]

            if pid != SSHD_PID and not isKnownHash(pcmd, pid):
                logging.info(f"checking of pid: {pid}:{pcmd}")
                o = {}
                o['uid'] = puid
                o['pid'] = pid
                o['ppid'] = ppid
                o['status'] = pstatus
                o['stime'] = pstime
                o['tty'] = ptty
                o['ptime'] = ptime
                o['cmd'] = pcmd
                o['comm'] = pcomm

                if publish_to_redis:
                    redisClient.publish(REDIS_CHANNEL_NAME, json.dumps(o))

        time.sleep(LOOPING_TIME)

def findSSHProcess():
    """
    This function will run to find the first ssh process. It will record its pid,
    and other information used to ignore this program.
    """

    global SSHD_PID

    ssh_proc_found = False
    logging.info('Finding SSH process')

    while not ssh_proc_found:
        res = container.top()
        for proc in res['Processes']:
            puid = proc[0]
            pid = proc[1]
            ppid = proc[2]
            pstatus = proc[3]
            pstime = proc[4]
            ptty = proc[5]
            ptime = proc[6]
            pcmd = proc[7]

            if pcmd == "/usr/sbin/sshd -D":
                ssh_proc_found = True
                o = {}
                o['uid'] = puid
                o['pid'] = pid
                o['ppid'] = ppid
                o['status'] = pstatus
                o['stime'] = pstime
                o['tty'] = ptty
                o['ptime'] = ptime
                o['cmd'] = pcmd

                SSHD_PID = pid

                logging.info(f'Found SSH pid: {SSHD_PID}, and stored it at key {REDIS_SSH_PROCESS}')
                redisClient.set(REDIS_SSH_PROCESS, json.dumps(o))
        time.sleep(0.1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "no_pub":
            publish_to_redis = False
            logging.info("not publishing to redis")

    # connect to the running target system
    targetName = getTargetContainerName()
    digestDict = loadDigest()
    cmdDigestDict = loadCmdDigest()

    while True:
        try:
            container = dockerClient.containers.get(targetName)
            if container:
                break
        except docker.errors.NotFound as e:
            logging.error("%s", e)
            time.sleep(5)

    findSSHProcess()
    runProcessLoop(container)
