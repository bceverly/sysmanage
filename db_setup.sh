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
