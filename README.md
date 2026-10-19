# Monitor components

This repository contains code to build and run a monitor component,
which is part of the ASGARD abstract model.

This monitor component collects two pieces of information on the target
system:

1) Resource consumption
2) Running processes

## Resource consumption
This component, represented by `metric.py`, uses a built-in tool `stats` 
from Docker to continuously gather values of resources consumed by a running container.

The statistics are temporarily stored in a Redis server which will be read later
by the decision engine through an intermediate monitor. The decision engine 
uses this information to decide which action to take.

The program reads its configuration from the `config.ini` file.
```ini
[metric]
metric_cpu_mem_avg_length = 10
```

* `metric_cpu_mem_avg_length` specifies the last `n` values of CPU and Memory consumption to calculate their average. This is to smooth out short-term fluctuations for that resource.

* For other resources such as network I/O and disk I/O, since they are accumulative values, the monitor stores their latest values.

## Running process
This component, represented by `process.py`, uses the Docker tool `top` to
query the running processes. The component also saves the process images
after it compares its digest SHA256 to a known list of digests.
If the digest is found to be different from a known list, its image will
be saved to a folder.

This helps to capture programs that are deleted from the target system
after they have been executed. This is one of the ways that attackers attempt
to protect their programs or to clean up an infected host machine.

The program reads its configuration from the `config.ini` file.
```ini
[process]
looping_time = 10
channel = channel_process
proc_path = /var/lib/proc
ignored_digest_file = /monitor/monitor/ignored_digest.txt
not_saved_digest_file = /monitor/monitor/not_saved_digest.txt
exe_dir_path = /monitor/monitor/exe
```

* `looping_time`: a delay in seconds before the `top` command is executed to gather the running processes.
* `channel`: a Redis channel to publish the list of running processes.
* `proc_path`: a path to read process images
* `ignored_digest_file`: a path to read a list of file digests `SHA256` which will be ignored.
* `not_saved_digest_file`: a path to read a list of file digests `SHA256` which are previously saved, such that they will not be saved again. This to avoid redundant file.
* `exe_dir_path`: directory where process images are saved.

## Terminate service
When there is a process to kill, the terminate program, which runs as a service
with root privileges, will read the pid from a Redis server and issue a kill command on the
host system.

First, make a copy of the systemd config file:
```sh
$ cp terminate.service.example terminate.service
```

Edit it accordingly, specifying where the terminate program is located. There should be a valid
Python virtual environment running.
```
[Unit]
Description=Program to terminate a process upon receiving the pid from Redis server

[Service]
Type=simple
ExecStart=/home/cowrie/repo/monitor_stats/env/bin/python /home/cowrie/repo/monitor_stats/terminate/terminate.py /home/cowrie/repo/monitor_stats/config-terminate.ini
ExecStop=kill -SIGTERM $MAINPID
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

To install this program, create a link to `/etc/systemd/system/terminate.service`:
```sh
$ sudo ln -s /home/cowrie/repo/monitor_stats/terminate.service /etc/systemd/system/terminate.service
```

After the installation, `systemd` has to be reloaded:
```sh
$ sudo systemctl daemon-reload
```

Then we need to enable the service:
```sh
$ sudo systemctl enable terminate.service
```

To run it, we can use systemd:
```sh
$ sudo systemctl start terminate
```

Check its status:
```sh
$ sudo systemctl status terminate
```

Stop the service:
```sh
$ sudo systemctl stop terminate
```

Disable the service:
```sh
$ sudo systemctl disable terminate
```

## Build Docker images

### Environment Variables
Create an environment variable file `.env` by copying `env.example`. The env file contains the host user ID that can access the Docker engine. Make sure this user ID is granted permission to connect to the Docker engine.
```bash
COWRIE_USER_ID=501
COWRIE_GROUP_ID=501
DOCKER_GROUP_ID=501
COWRIE_USER=501:501
```

### docker-compose

* Create a `docker-compose.yml` file by copying `docker-compose.yml.example`.
* Run `docker compose build` to create two images: `monitor_metric` and `monitor_process`.