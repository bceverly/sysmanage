# SysManage
Cross platform system monitoring and management service

SysManage is a python application that allows you to have remote servers
in a variety of supported operating systems (Linux, Windows, MacOS, FreeBSD and
OpenBSD) that have an agent installedon them (SysManage Agent) that will
connect with this service and provide the following functions:

- Periodically check in and allow the server to identify that a remote agent
has lost connectivity (i.e. the remote machine might be "down")
- Keep track of any updates that might be available for the remote server
- Install updates on the remote server

# Building
To build this project, you need to be running python 3.12 or higher in a 
virtual environment with the following items installed:

- python3 -m pip install -r requirements.txt
- Install liquibase with JavaJRE 17 per your operating system
- Install PostgreSQL version 14 or higher 

Please see LICENSE for licensing of this service.
