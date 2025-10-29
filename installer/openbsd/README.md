# OpenBSD Port for SysManage Server

This directory contains the OpenBSD port infrastructure for SysManage Server.

## Building the Port

OpenBSD uses a ports system rather than pre-built packages. To create a port tarball:

```sh
make installer-openbsd
```

This will create a tarball in `installer/dist/` containing the complete port infrastructure.

## Installing from Port

1. Extract the port tarball to your ports tree:
```sh
cd /usr/ports/mystuff
mkdir -p www
tar xzf /path/to/sysmanage-openbsd-port-*.tar.gz -C www/
```

2. Generate checksums:
```sh
cd /usr/ports/mystuff/www/sysmanage
doas make makesum
```

3. Build and install:
```sh
doas make install
```

## Configuration

1. Initialize PostgreSQL database (if not already done):
```sh
doas su - _postgresql
initdb -D /var/postgresql/data -U postgres -A scram-sha-256 -E UTF8 -W
exit
doas rcctl enable postgresql
doas rcctl start postgresql
```

2. Create database and user:
```sh
doas su - _postgresql -c "createuser -P sysmanage"
doas su - _postgresql -c "createdb -O sysmanage sysmanage"
```

3. Configure SysManage:
```sh
doas vi /etc/sysmanage.yaml
```

Update the database connection string:
```yaml
database:
  url: "postgresql://sysmanage:password@localhost/sysmanage"
```

4. Initialize database schema:
```sh
cd /usr/local/libexec/sysmanage
doas python3 -m alembic upgrade head
```

5. Enable and start the service:
```sh
doas rcctl enable sysmanage
doas rcctl start sysmanage
```

## Accessing the Web Interface

By default, SysManage Server listens on port 8080:
- http://your-server:8080

## Dependencies

Required packages (automatically installed):
- PostgreSQL
- Python 3 with modules:
  - py3-sqlalchemy
  - py3-alembic
  - py3-psycopg2
  - py3-websockets
  - py3-aiohttp
  - py3-fastapi
  - py3-uvicorn
  - py3-cryptography
  - py3-yaml
  - py3-babel

## Port Submission

To submit this port to OpenBSD:

1. Register user and group in `/usr/ports/infrastructure/db/user.list`:
```
828 _sysmanage    _sysmanage    SysManage Server
```

2. Update PLIST with actual file list:
```sh
cd /usr/ports/mystuff/www/sysmanage
make update-plist
```

3. Test thoroughly on -current and -stable

4. Submit to ports@openbsd.org

## Notes

- The frontend must be pre-built before creating the port tarball
- Frontend files are served from `/usr/local/share/sysmanage/frontend/`
- Backend runs from `/usr/local/libexec/sysmanage/`
- Configuration is in `/etc/sysmanage.yaml`
- Logs go to `/var/log/sysmanage/`
- Database state in `/var/db/sysmanage/`
