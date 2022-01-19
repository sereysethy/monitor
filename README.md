# Create virtual environment

This repository contains codes to build and run a monitor that use a built-in
metric collector `stats` from Docker to gather statistics of ressources used
by a container.

The statistics will be stored temporarily in a redis server to be read later
by the learning agent, which uses this information to decide on which action to
take.