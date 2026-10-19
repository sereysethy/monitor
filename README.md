# Monitor Components

This repository contains the code to build and run the **monitor component**, part of the
[Asgard2](#about-asgard2) adaptive and self-guarded honeypot. The monitor collects information
from a target system (a Docker container) and makes it available to the decision engine.

## Contents

- [About Asgard2](#about-asgard2)
- [Architecture overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Redis setup](#redis-setup)
- [Configure the target container](#configure-the-target-container)
- [Build and run the Docker images](#build-and-run-the-docker-images)
- [Metric monitor (resource consumption)](#metric-monitor-resource-consumption)
- [Process monitor (running processes)](#process-monitor-running-processes)
- [Terminate service](#terminate-service)
- [Security considerations](#security-considerations)
- [License and contributing](#license-and-contributing)

## About Asgard2

ASGARD is an abstract model for an adaptive and self-guarded honeypot. An adaptive
and self-guarded honeypot is designed to collect as much attack data as possible
while preventing the attacker from deeply compromising the system.
The model can be used to instantiate different types of adaptive and self-guarded honeypot.
*Asgard2* is an instance of the model. It uses deep reinforcement learning to learn
to engage with attackers to achieve its two objectives.

Read more details on its [project page](https://github.com/sereysethy/asgard).

## Architecture overview

The monitor gathers two kinds of information and a separate service acts on the decision engine's output:

| Component | Script | Purpose | Output |
|-----------|--------|---------|--------|
| Metric monitor | `metric.py` | Collects CPU, memory, network I/O and disk I/O of a container | Stored in Redis |
| Process monitor | `process.py` | Lists running processes and saves unknown process images | Published on a Redis channel |
| Terminate service | `terminate/terminate.py` | Kills a host process by PID | Subscribes to a Redis channel for PIDs |

![Architecture diagram showing the interaction between the monitor, target system and the decision engine.](images/Asgard2_monitor.svg)

## Prerequisites

- Linux host with Docker Engine and Docker Compose v2 (`docker compose`)
- A Redis server (provided by `docker-compose.yml`) reachable by the monitors and the terminate service
- Python 3 with `venv` (required for the terminate service)
- A host user that is allowed to access the Docker engine

## Redis setup

All components exchange data through Redis. The host and port configured in each
component's config file must match the Redis server.

Redis is defined as a service in `docker-compose.yml`, so `docker compose up -d` starts it
together with the monitors (see [Build and run the Docker images](#build-and-run-the-docker-images)).
To let the terminate service reach it from the host, publish its port on the loopback
interface only: `127.0.0.1:6379:6379`. Containers reach Redis by its service name
(`host = redis`), while the systemd service on the host uses `127.0.0.1`.

Redis connection settings are in the `[redis]` section of `config.ini`:

```ini
[redis]
host = redis
port = 6379
```

Data written by the monitors:

* The monitor publishes the list of running processes on the channel set by `channel`
  in the `[process]` section.

```ini
[process]
channel = channel_process
```

* Keys under which resource consumption is written:

```python
keys = [
    'list_cpu_usage_per',
    'list_mem_usage_per',
    'cpu_usage_per',
    'mem_usage_per',
    'net_in_byte',
    'net_out_byte',
    'blk_read_byte',
    'blk_write_byte'
]
```

**Redis must not be exposed to untrusted networks.** See [Security considerations](#security-considerations).

## Configure the target container

Select the container to monitor and set how the monitor reaches the Docker engine in `config.ini`:

```ini
[docker]
uri = unix:///var/run/docker.sock
debug = 1

[target_system]
container_name = honeypot
network_interface = eth0
```

* `uri`: URI of the Docker engine socket. The socket file must be mounted into the monitor containers at the same path in `docker-compose.yml`.
* `debug`: `1` prints the collected metrics, `0` disables it.
* `container_name`: name of the target container to monitor.
* `network_interface`: network interface inside the target container used to measure network I/O.

## Build and run the Docker images

### Environment variables

Create the environment file by copying the example:

```bash
cp env.example .env
```

The file holds the host user and group IDs used to access the Docker engine:

```bash
COWRIE_USER_ID=501
COWRIE_GROUP_ID=501
DOCKER_GROUP_ID=501
COWRIE_USER=501:501
```

The values above are examples. Replace them with the real IDs on your host:

```bash
id -u                      # user ID      -> COWRIE_USER_ID
id -g                      # group ID     -> COWRIE_GROUP_ID
getent group docker        # docker group -> DOCKER_GROUP_ID
```

`COWRIE_USER` is the combined `UID:GID` value. The `COWRIE_` prefix refers to the
[Cowrie](https://github.com/cowrie/cowrie) honeypot environment this monitor was built for.
The user must be granted permission to connect to the Docker engine.

### docker-compose

1. Create the compose file by copying the example:
   ```bash
   cp docker-compose.yml.example docker-compose.yml
   ```
2. Build the two images, `monitor_metric` and `monitor_process`:
   ```bash
   docker compose build
   ```
3. Start the monitors:
   ```bash
   docker compose up -d
   ```
4. Check the logs:
   ```bash
   docker compose logs -f
   ```

## Metric monitor (resource consumption)

`metric.py` uses the built-in Docker `stats` tool to continuously gather the resources
consumed by a running container.

The statistics are temporarily stored in Redis. The decision engine reads them later through
an intermediate monitor and uses them to decide which action to take.

The program reads its configuration from `config.ini`:

```ini
[metric]
metric_cpu_mem_avg_length = 10
```

| Option | Description |
|--------|-------------|
| `metric_cpu_mem_avg_length` | Number of the most recent samples (not seconds) used to compute the average CPU and memory consumption. This smooths out short-term fluctuations. The time window covered depends on how often Docker `stats` reports. |

Network I/O and disk I/O are cumulative counters, so for those resources the monitor stores
only the latest value.

## Process monitor (running processes)

`process.py` uses the Docker `top` tool to query the running processes. For each process,
it compares the SHA256 digest of the process image against two lists of known digests:
programs to ignore and images already saved. If the digest is in neither, the image is saved to a folder.

This captures programs that are deleted from the target system after they have been executed,
which is one way attackers hide their programs or clean up an infected host.

The program reads its configuration from `config.ini`:

```ini
[process]
looping_time = 10
channel = channel_process
proc_path = /var/lib/proc
ignored_digest_file = /monitor/monitor/ignored_digest.txt
not_saved_digest_file = /monitor/monitor/not_saved_digest.txt
exe_dir_path = /monitor/monitor/exe
```

| Option | Description |
|--------|-------------|
| `looping_time` | Delay in seconds between executions of `top` to gather the running processes. |
| `channel` | Redis channel on which the list of running processes is published. |
| `proc_path` | Path from which process images are read. This is the location where the host's process filesystem is made available to the container. |
| `ignored_digest_file` | File listing SHA256 digests of programs to ignore, such as the `sshd` daemon and `/bin/bash`. These digests are checked before an image is saved, so matching programs are not saved. |
| `not_saved_digest_file` | File listing SHA256 digests whose images are already saved. This ensures each unique binary is saved only once. Matching uses only the digest, not the path. |
| `exe_dir_path` | Directory where process images are saved. |

**Note:** `ignored_digest_file` and `not_saved_digest_file` contain one entry per line, in this format:

```txt
/file/path/to/binary:SHA256
```

For example, the following is the content of `ignored_digest_file`:

```
/bin/bash:059fce560704769f9ee72e095e85c77cbcd528dc21cc51d9255cfe46856b5f02
/usr/sbin/sshd:c4805c50ad0a298f2d46d316dd7a85a789ccd958c9c9155ab4d49fc6c94efa1d
```

## Terminate service

When the decision engine decides a process must be killed, the intermediate monitor publishes
the host PID (an integer) on a Redis channel defined in the `[terminate]` section. The terminate
program subscribes to that channel and issues a kill command on the host. It runs as a systemd
service with root privileges.

PIDs are delivered over a Redis channel, so a PID published while the service is stopped is not delivered.

### 1. Create a Python virtual environment

```bash
cd /path/to/monitor        # the repository root
python3 -m venv env
./env/bin/pip install -r requirements.txt
```

### 2. Create the terminate configuration

The service is started with a separate config file `config-terminate.ini`.
It must contain a `[redis]` section and a `[terminate]` section.

```ini
[redis]
host = 127.0.0.1
port = 6379

[terminate]
channel_name = channel_terminate
looping_time = 2
```

* `channel_name`: Redis channel on which PIDs are published.
* `looping_time`: number of seconds the terminate program sleeps when there are no PIDs to kill.

### 3. Create and edit the systemd unit

Copy the example unit file **in the repository**, then edit it **before** linking it into
systemd. Replace `/path/to/monitor` with the absolute path of your checkout.

```bash
cp terminate.service.example terminate.service
```

```ini
[Unit]
Description=Program to terminate a process upon receiving the pid from Redis server

[Service]
Type=simple
ExecStart=/path/to/monitor/env/bin/python /path/to/monitor/terminate/terminate.py /path/to/monitor/config-terminate.ini
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

systemd stops the service with `SIGTERM` by default, so no `ExecStop` line is needed.
All paths must be absolute; a wrong path makes the service fail to start.

### 4. Install and start

Link the unit into systemd using absolute paths, reload systemd, then enable and start it:

```bash
sudo ln -s /path/to/monitor/terminate.service /etc/systemd/system/terminate.service
sudo systemctl daemon-reload
sudo systemctl enable --now terminate.service
```

### Manage the service

```bash
sudo systemctl status terminate     # check status
sudo journalctl -u terminate -f     # follow logs
sudo systemctl stop terminate       # stop
sudo systemctl disable terminate    # disable at boot
```

## Security considerations

- **Keep Redis private.** The terminate service runs as root and kills any PID it receives
  from Redis. Anyone who can publish to that Redis instance can terminate arbitrary host
  processes. Publish its port on the loopback interface only (`127.0.0.1:6379:6379`) and do
  not expose it to other networks.
- **Docker access is root-equivalent.** Access to the Docker engine (including a mounted
  Docker socket) is effectively root access to the host. Grant it only to the dedicated user
  and containers that need it.
- **Saved process images may be malware.** The directory set by `exe_dir_path` can contain
  attacker binaries. Do not execute them, restrict permissions on the folder, and analyze
  them only in an isolated environment.

## License and contributing

This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.

Contributions are welcome.

- **Bugs and questions:** open an issue and include your OS, Docker version,
  the relevant part of your config files, and any logs.
- **Changes:** fork the repository, create a branch, and open a pull request
  that explains what changed and why. Please keep each pull request focused
  on a single change.
- **Testing:** describe how you tested your change (for example, which
  target container you ran the monitors against).
- **License:** by submitting a contribution, you agree that it is released
  under the [GPL v3.0](LICENSE) license of this project.
