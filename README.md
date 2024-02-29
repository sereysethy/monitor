# Create virtual environment

This repository contains codes to build and run a monitor that use a built-in
metric collector `stats` from Docker to gather statistics of ressources used
by a container.

The statistics will be stored temporarily in a redis server to be read later
by the learning agent, which uses this information to decide on which action to
take.

# Terminate service
When there is a process to kill, the terminate program which is run as a service
as a root will read the pid from a redis server and issue a kill command on the
host system.

First make a copy for the systemd config system

```sh
$ cp terminate.service.example terminate.service
```

Edit it accordingly like where is the terminate program, there should be a valid
python virtual environment running.

```
[Unit]
Description=Program to termniate a process upon receiving the pid from Redis server

[Service]
Type=simple
ExecStart=/home/cowrie/repo/monitor_stats/env/bin/python /home/cowrie/repo/monitor_stats/terminate/terminate.py /home/cowrie/repo/monitor_stats/config-terminate.ini
ExecStop=kill -SIGTERM $MAINPID
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

To install this program, make a link to `/etc/systemd/system/terminate`

```sh
$ sudo ln -s /home/cowrie/repo/monitor_stats/terminate.service /etc/systemd/system/terminate.service
```

To run it, we can use a service of systemd.

```sh
$ systemctl start terminate
```

Check its status

```sh
$ systemctl status terminate
```

Stop the service

```sh
$ systemctl stop terminate
```