#! /bin/bash

echo "This script generates two files.  One is called createdb.sh and it"
echo "is a script that will perform the necessary bootstrapping of the"
echo "PostgreSQL database.  The second file is called sysmanage.yaml and"
echo "it should be reviewed and placed in the /etc directory.  Note that"
echo "the permissions on the file should NOT be set to world read as it"
echo "contains secrets used by SysManage."
echo ""
echo "The complete list of environment variables you need to set in order"
echo "to successfully run this script is:"
echo ""
echo "SYSMANAGE_WEBHOST"
echo "SYSMANAGE_WEBPORT"
echo "SYSMANAGE_APIPORT"
echo "SYSMANAGE_DBHOST"
echo "SYSMANAGE_DBPORT"
echo "SYSMANAGE_DBUSER"
echo "SYSMANAGE_DBPASSWORD"
echo "SYSMANAGE_DATABASE"
echo "SYSMANAGE_ADMINUSER"
echo "SYSMANAGE_ADMINPASSWORD"
echo ""

if [[ -z "${SYSMANAGE_WEBHOST}" ]]; then
    echo "You must set SYSMANAGE_WEBHOST to the name of your web server"
    echo "hostname or IP:"
    echo ""
    echo "$ export SYSMANAGE_WEBHOST='webhostname'"
    exit 1
fi

if [[ -z "${SYSMANAGE_WEBPORT}" ]]; then
    echo "You must set SYSMANAGE_WEBPORT to the name of your web server"
    echo "network port:"
    echo ""
    echo "$ export SYSMANAGE_WEBPORT='webport'"
    exit 1
fi

if [[ -z "${SYSMANAGE_APIPORT}" ]]; then
    echo "You must set SYSMANAGE_APIPORT to the name of your api server"
    echo "network port:"
    echo ""
    echo "$ export SYSMANAGE_APIPORT='apiport'"
    exit 1
fi

if [[ -z "${SYSMANAGE_DBHOST}" ]]; then
    echo "You must set SYSMANAGE_DBHOST to the name of your PostgreSQL"
    echo "database hostname or IP:"
    echo ""
    echo "$ export SYSMANAGE_DBHOST='dbhostname'"
    exit 1
fi

if [[ -z "${SYSMANAGE_DBPORT}" ]]; then
    echo "You must set SYSMANAGE_DBPORT to the name of your PostgreSQL"
    echo "database server port number:"
    echo ""
    echo "$ export SYSMANAGE_DBPORT='5432'"
    exit 1
fi

if [[ -z "${SYSMANAGE_DBUSER}" ]]; then
    echo "You must set SYSMANAGE_DBUSER to the name of your PostgreSQL"
    echo "database server username:"
    echo ""
    echo "$ export SYSMANAGE_DBUSER='dbuser'"
    exit 1
fi

if [[ -z "${SYSMANAGE_DBPASSWORD}" ]]; then
    echo "You must set SYSMANAGE_DBPASSWORD to the name of your PostgreSQL"
    echo "database server password:"
    echo ""
    echo "$ export SYSMANAGE_DBPASSWORD='dbpassword'"
    exit 1
fi

if [[ -z "${SYSMANAGE_DATABASE}" ]]; then
    echo "You must set SYSMANAGE_DATABASE to the name of your PostgreSQL"
    echo "database:"
    echo ""
    echo "$ export SYSMANAGE_DATABASE='dbname'"
    exit 1
fi

if [[ -z "${SYSMANAGE_ADMINUSER}" ]]; then
    echo "You must set SYSMANAGE_ADMINUSER to the name of your SysManage"
    echo "administrative user:"
    echo ""
    echo "$ export SYSMANAGE_ADMINUSER='adminname'"
    exit 1
fi

if [[ -z "${SYSMANAGE_ADMINPASSWORD}" ]]; then
    echo "You must set SYSMANAGE_ADMINPASSWORD to the name of your SysManage"
    echo "administrative user password:"
    echo ""
    echo "$ export SYSMANAGE_ADMINPASSWORD='adminpassword'"
    exit 1
fi

# Made it to here, all of the environment variables are set
# Test to see if we have psql in our path

psql --version > /dev/null 2>&1

if [[ $? -ne 0 ]]; then
    echo "You need to install PostgreSQL and ensure that psql is in your path"
    exit 1
fi

if [[ `uname` == 'Darwin' ]]; then
    PSQLCMD="psql -h ${SYSMANAGE_DBHOST} -p ${SYSMANAGE_DBPORT}"
fi

if [[ `uname` == 'Linux' ]]; then
    echo "This script will be using sudo so please type your password if"
    echo "prompted..."
    PSQLCMD="sudo -u postgres psql -h ${SYSMANAGE_DBHOST} -p ${SYSMANAGE_DBPORRT}"
fi

# Create the database and user creation script
echo "${PSQLCMD} -d postgres -c \"create role ${SYSMANAGE_DBUSER} with login password '${SYSMANAGE_DBPASSWORD}';\"" > createdb.sh
echo "${PSQLCMD} -d postgres -c \"alter role ${SYSMANAGE_DBUSER} CREATEDB;\"" >> createdb.sh
echo "${PSQLCMD} -d postgres -c \"create database ${SYSMANAGE_DATABASE};\"" >> createdb.sh
echo "${PSQLCMD} -d postgres -c \"grant connect on database ${SYSMANAGE_DATABASE} to ${SYSMANAGE_DBUSER};\"" >> createdb.sh
echo "${PSQLCMD} -d postgres -c \"grant all privileges on database ${SYSMANAGE_DATABASE} to ${SYSMANAGE_DBUSER};\"" >> createdb.sh
echo "${PSQLCMD} -d ${SYSMANAGE_DATABASE} -c \"grant all on schema public to ${SYSMANAGE_DBUSER};\"" >> createdb.sh

echo "network:" > sysmanage.yaml
echo "  hostName: \"${SYSMANAGE_WEBHOST}\"" >> sysmanage.yaml
echo "  webPort: ${SYSMANAGE_WEBPORT}" >> sysmanage.yaml
echo "  tlsCertFile: \"TLS_Certificate_File\"" >> sysmanage.yaml
echo "  apiPort: ${SYSMANAGE_APIPORT}" >> sysmanage.yaml
echo "" >> sysmanage.yaml
echo "database:" >> sysmanage.yaml
echo "  user: \"${SYSMANAGE_DBUSER}\"" >> sysmanage.yaml
echo "  password: \"${SYSMANAGE_DBPASSWORD}\"" >> sysmanage.yaml
echo "  host: \"${SYSMANAGE_DBHOST}\"" >> sysmanage.yaml
echo "  port: \"${SYSMANAGE_DBPORT}\"" >> sysmanage.yaml
echo "  name: \"${SYSMANAGE_DATABASE}\"" >> sysmanage.yaml
echo "" >> sysmanage.yaml
echo "security:" >> sysmanage.yaml
SALT=`openssl rand -base64 32`
echo "  password_salt: \"${SALT}\"" >> sysmanage.yaml
echo "  admin_userid: \"${SYSMANAGE_ADMINUSER}\"" >> sysmanage.yaml
echo "  admin_password: \"${SYSMANAGE_ADMINPASSWORD}\"" >> sysmanage.yaml
