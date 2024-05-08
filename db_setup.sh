#! /bin/bash

echo "This script will create a PostgreSQL database user and a database"
echo "for use by SysManage.  It need only be ran one time and then a file"
echo "will be generated in the current directory that can be used as the"
echo "/etc/sysmanage.yaml file, containing the necessary configuration and"
echo "secrets for the server process to run successfully."
echo ""
echo "This script need only be ran one time."
echo ""
echo "The complete list of environment variables you need to set in order"
echo "to successfully run this script is:"
echo ""
echo "SYSMANAGE_DBHOST"
echo "SYSMANAGE_DBPORT"
echo "SYSMANAGE_DBUSER"
echo "SYSMANAGE_DBPASSWORD"
echo "SYSMANAGE_DATABASE"
echo ""

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
echo "  hostName: \"FQDN\"" >> sysmanage.yaml
echo "  webPort: 80" >> sysmanage.yaml
echo "  tlsCertFile: \"TLS_Certificate_File\"" >> sysmanage.yaml
echo "  apiPort: 8000" >> sysmanage.yaml
echo "" >> sysmanage.yaml
echo "database:" >> sysmanage.yaml
echo "  user: \"db_user\"" >> sysmanage.yaml
echo "  password: \"db_password\"" >> sysmanage.yaml
echo "  host: \"db_fqdn\"" >> sysmanage.yaml
echo "  port: \"db_service_port\"" >> sysmanage.yaml
echo "  name: \"db_database_name\"" >> sysmanage.yaml
echo "" >> sysmanage.yaml
echo "security:" >> sysmanage.yaml
echo "  password_salt: \"the salt value\"" >> sysmanage.yaml
echo "  admin_userid: \"hardcoded_admin_login\"" >> sysmanage.yaml
echo "  admin_password: \"password_for_above\"" >> sysmanage.yaml
