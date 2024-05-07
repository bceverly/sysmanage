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
- Install PostgreSQL version 14 or higher
    - Create a database user
    - Create a new database
    - Grant the new user permissions on the new database
- Using the sysmanage.yaml.example file, create a file called 
/etc/sysmanage.yaml
    - Store the DB credentials in a file named /etc/sysmanage.yaml
    - Generate a new salt value ($ openssl rand -base64 32)
    - Store the salt value created above in the /etc/sysmanage.yaml file as
password_salt (See sample file in root directory for an example)
    - Set up the admin userid and password in the /etc/sysmanage.yaml file
    - Run the web UI via "python3 -m http.server" from the ./website
directory
- Migrate to the latest database schema with "alembic upgrade head"

Please see LICENSE for licensing of this service.
