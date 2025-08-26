# SysManage Server

[![CI/CD Pipeline](https://github.com/bceverly/sysmanage/actions/workflows/ci.yml/badge.svg)](https://github.com/bceverly/sysmanage/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-BSD%202--Clause-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linting](https://img.shields.io/badge/linting-pylint-blue.svg)](https://github.com/PyCQA/pylint)

Cross platform system monitoring and management service

SysManage is a python application that allows you to have remote servers
in a variety of supported operating systems (Linux, Windows, MacOS, FreeBSD and
OpenBSD) that have an agent installedon them (SysManage Agent) that will
connect with this service and provide the following functions:

- Periodically check in and allow the server to identify that a remote agent
has lost connectivity (i.e. the remote machine might be "down")
- Keep track of any updates that might be available for the remote server
- Install updates on the remote server

Please see LICENSE for licensing of this service.

# Building
To build this project, you need to be running python 3.12 or higher in a 
virtual environment with the following items installed:

- python3 -m pip install -r requirements.txt
- Install PostgreSQL version 14 or higher
- Run db_setup.sh to generate the createdb.sh script and the
sysmanage.yaml file (copy it to /etc)
- Migrate to the latest database schema with "alembic upgrade head"
- Make sure your /etc/hosts file has entries in it for the URLs you are
using for the website and the API
- Run 'npm install' to install the dependencies the project needs in the
./frontend directory
- Run the web UI via "npm start" from the ./frontend
directory
- Run the backend API with "uvicorn backend.main:app"
- Run the unit tests with "pytest"

# Database Migration
Edit the persistence/models.py file to define new database tables or
columns.  Afterwards, execute:

(.venv) $ alembic revision --autogenerate -m "describe the changes"

(.venv) $ alembic upgrade head

If you need to roll back a migration, you can run:

(.venv) $ alembic downgrade <revision>

or

(.venv) $ alembic downgrade -1

The following command shows the history of migrations:

(.venv) $ alembic history

# API Call Flow

To use the API, first call the /login method.  A response body will be
returned containing a JSON value called X_Reauthorization.  This is the
"bearer token" that will be used to validate privileged API calls from that
point forward.

On the next API call to a privileged API, set a header called
Authorization with a value of the word "Bearer" followed by the token
you received from the response body to /login.  For example, if you
were using curl:

curl -X 'GET' 'https://localhost:8000/users' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer xxxxxxxxxxx'

where the x's in the "Authorization" header are the value of the token
you received from the call to /login.  If successful, this call will return
an HTTP response header called "X_Reauthorization" which contains the token
you will use on your next call and so on.

A token can only be used one time and even if it is unexpired, it will be
deny-listed on the server and prevent a subsequent successful re-use of the
same token.  Any bad or attempted re-use of tokens will result in a response
code of 403 (Forbidden).

To access the OpenAPI swagger documentation for SysManage, run the service
as follows:

(.venv) % uvicorn backend.main:app --reload

You can then point your browser at the URL/API port specified in the file at
/etc/sysmanage.yaml, followed by the docs path.  For example:

http://127.0.0.1:8000/docs

# Front-end

The front-end is written in React.JS and can be executve in a local
environment by navigating to the "website" directory and running:

$ npm start
