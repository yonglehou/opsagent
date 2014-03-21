#!/bin/bash
##
## @author: Thibault BRONCHAIN
## (c) 2014 MadeiraCloud LTD.
##

if [ "$1" != "update" ]; then
    # RW set variables
    APP_ID=@{app_id}
    WS_URI=@{ws_uri}
    VERSION=@{version}
    BASE_REMOTE=@{remote}
    GPG_KEY_URI=@{gpg_key_uri}
fi

# opsagent config directory
OA_CONF_DIR=/var/lib/madeira/opsagent
# ops agent watch files crc directory
OA_WATCH_DIR=${OA_CONF_DIR}/watch
# opsagent logs directory
OA_LOG_DIR=/var/log/madeira
# opsagent URI
#BASE_REMOTE=https://s3.amazonaws.com/visualops
OA_REMOTE="${BASE_REMOTE}/${VERSION}"
OA_GPG_KEY="${OA_CONF_DIR}/madeira.pub"

# OpsAgent directories
OA_ROOT_DIR=/opt/madeira
OA_BOOT_DIR=${OA_ROOT_DIR}/bootstrap
OA_ENV_DIR=${OA_ROOT_DIR}/env

# internal var
OA_EXEC_FILE=/tmp/opsagent.boot

mkdir -p {$OA_LOG_DIR,$OA_CONF_DIR}

# bootstrap
cat <<EOF > ${OA_CONF_DIR}/cron.sh
#!/bin/bash
##
## @author: Thibault BRONCHAIN
## (c) 2014 MadeiraCloud LTD.
##

#ulimit -S -c 0

export OA_EXEC_FILE=${OA_EXEC_FILE}
export OA_LOG_DIR=${OA_LOG_DIR}

if [ \$(cat \${OA_LOG_DIR}/bootstrap.log | wc -l) -gt 1000 ]; then
    cp -f \${OA_LOG_DIR}/bootstrap.log \${OA_LOG_DIR}/bootstrap.log.old
    echo -n > \${OA_LOG_DIR}/bootstrap.log
    chown root:root \${OA_LOG_DIR}/bootstrap.log.old
    chmod 640 \${OA_LOG_DIR}/bootstrap.log.old
fi

if [ -f \${OA_EXEC_FILE} ]; then
    OLD_PID="\$(cat \${OA_EXEC_FILE})"
    if [ \$(ps -eo pid,comm | tr -d ' ' | grep \${OLD_PID} | wc -l) -ne 0 ]; then
        echo "Bootstrap already running ..."
        exit 0
    else
        rm -f \${OA_EXEC_FILE}
    fi
fi

export OA_CONF_DIR=${OA_CONF_DIR}
export OA_WATCH_DIR=${OA_WATCH_DIR}
export OA_REMOTE=${OA_REMOTE}

export OA_ROOT_DIR=${OA_ROOT_DIR}
export OA_BOOT_DIR=${OA_BOOT_DIR}
export OA_ENV_DIR=${OA_ENV_DIR}

export OA_GPG_KEY=${OA_GPG_KEY}

export APP_ID=${APP_ID}
export WS_URI=${WS_URI}
export VERSION=${VERSION}
export BASE_REMOTE=${BASE_REMOTE}
export GPG_KEY_URI=${GPG_KEY_URI}

# set working file
ps -eo pid,comm | tr -d ' ' | grep "^\$$" > \${OA_EXEC_FILE}

# Set bootstrap log with restrictive access rights
if [ ! -f \${OA_LOG_DIR}/bootstrap.log ]; then
    touch \${OA_LOG_DIR}/bootstrap.log
fi
chown root:root \${OA_LOG_DIR}/bootstrap.log
chmod 640 \${OA_LOG_DIR}/bootstrap.log

curl -sSL -o \${OA_GPG_KEY} \${GPG_KEY_URI}
chmod 440 \${OA_GPG_KEY}

curl -sSL -o \${OA_CONF_DIR}/init.sh \${OA_REMOTE}/init.sh
chmod 750 \${OA_CONF_DIR}/init.sh
gpg --verify \${OA_GPG_KEY} \${OA_CONF_DIR}/init.sh

if [ $? -eq 0 ]; then
    bash \${OA_CONF_DIR}/init.sh
    EXIT=\$?
else
    echo "init checksum check failed, exiting ..." >&2
    EXIT=1
fi

rm -f \${OA_EXEC_FILE}
exit \${EXIT}
EOF

# set cron
chown root:root ${OA_CONF_DIR}/cron.sh
chmod 540 ${OA_CONF_DIR}/cron.sh
CRON=$(grep ${OA_CONF_DIR}/cron.sh /etc/crontab | wc -l)
if [ $CRON -eq 0 ]; then
    echo "*/1 * * * * ${OA_CONF_DIR}/cron.sh >> ${OA_LOG_DIR}/bootstrap.log 2>&1" | crontab
fi

#((${OA_CONF_DIR}/cron.sh >> ${OA_LOG_DIR}/bootstrap.log 2>&1)&)&

# EOF
