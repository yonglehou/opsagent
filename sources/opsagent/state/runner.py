'''
VisualOps agent state runner
(c) 2014 - MadeiraCloud LTD.

@author: Michael (michael@mc2.io)
'''

import os
import json

from salt.state import State as RunState

from opsagent import utils
from opsagent.exception import ExecutionException

class StateRunner(object):

    spec_mods = ['npm', 'pip', 'gem', 'docker']

    def __init__(self, config):

        self.state = None
        self.config = config

        # init salt opts
        self._init_opts(config)

        # change config to salt config
        config = config.get("salt",{})

        # init custom os type
        self._init_cust_ostype()

        # init state
        self._init_state()

        # init os type
        self._init_ostype()

        # pkg cache dir
        self._pkg_cache = (config['pkg_cache'] if 'pkg_cache' in config and config['pkg_cache'] and isinstance(config['pkg_cache'], basestring) else '/tmp/')

    def _init_opts(self, config):
        salt_config = config.get('salt',{})

        self._salt_opts = {
            'file_client':       'local',
            'renderer':          'yaml_jinja',
            'failhard':          False,
            'state_top':         'salt://top.sls',
            'nodegroups':        {},
            'file_roots':        {'base': [ ]},
            'state_auto_order':  False,
            'extension_modules': None,
            'id':                '',
            'pillar_roots':      '',
            'cachedir':          None,
            'test':              False,
            'environment':       None,
            'watch_dir':         config['global']['watch'],
        }

        if salt_config.get('runtime'):
            self._salt_opts.update(salt_config['runtime'])

        # file roots
        for path in salt_config['srv_root'].split(':'):
            # check and make path
            if not self.__mkdir(path):
                continue

            self._salt_opts['file_roots']['base'].append(path)

        if len(self._salt_opts['file_roots']['base']) == 0:     raise ExecutionException("Missing file roots argument")
        if not self.__mkdir(salt_config['extension_modules']):       raise ExecutionException("Missing extension modules argument")

        self._salt_opts['extension_modules'] = salt_config['extension_modules']

        if not self.__mkdir(salt_config['cachedir']):    raise ExecutionException("Missing cachedir argument")

        self._salt_opts['cachedir'] = salt_config['cachedir']

    def _init_state(self):
        """
            Init salt state object.
        """

        self.state = RunState(self._salt_opts)

    def _init_cust_ostype(self):
        try:
            import subprocess

            config_file = self.__is_existed(['/etc/issue', '/etc/redhat-release'])
            if not config_file:
                    raise ExecutionException("Cannot find the system config file")

            cmd = 'grep -io -E  "ubuntu|debian|centos|redhat|red hat|amazon" ' + config_file
            process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)

            out, err = process.communicate()

            if process.returncode != 0:
                    utils.log("ERROR", "Excute cmd %s failed..."%cmd, ("_init_cust_ostype", self))
                    raise ExecutionException("Excute cmd %s failed"%cmd)

            self._salt_opts['cust_ostype'] = out.lower().replace(" ","")
        except Exception, e:
            utils.log("ERROR", "Fetch custom agent's os type failed...", ("_init_cust_ostype", self))

    def _init_ostype(self):
        try:
            self.os_type = (self.state.opts['grains']['os'].lower()
                            if self.state.opts
                            and 'grains' in self.state.opts
                            and 'os' in self.state.opts['grains']
                            else 'unknown')

            self.os_release = (self.state.opts['grains']['osrelease'].lower()
                            if self.state.opts
                            and 'grains' in self.state.opts
                            and 'osrelease' in self.state.opts['grains']
                            else 'unknown')

            if self.os_type == 'unknown':
                if self._salt_opts.get('cust_ostype') is None:
                    raise Exception
                else: self.os_type = self._salt_opts['cust_ostype']

        except Exception, e:
            utils.log("ERROR", "Fetch agent's os type failed...", ("_init_ostype", self))
            raise ExecutionException("Fetch agent's os type failed")

    def exec_salt(self, states):
        """
            Transfer and exec salt state.
            return result format: (result,comment,out_log), result:True/False
        """

        result = False
        comment = ''
        out_log = ''

        # check
        if not states:
            out_log = "Null states"
            return (result, comment, out_log)
        if not states or not isinstance(states, list):
            out_log = "Invalid state format %s" % str(states)
            return (result, comment, out_log)

        # check whether contain specail module
        try:
            mods = self.get_mods(states)

            # whether special module
            inter_mods = list(set(mods).intersection(set(self.spec_mods)))
            if len(inter_mods)>0:
                self._enable_epel()

                # pre-installed npm
                if 'npm' in inter_mods:
                    if self.os_type in ['redhat', 'centos'] and float(self.os_release) >= 7.0 or self.os_type == 'debian':
                        self.__preinstall_npm()

        except Exception, e:
            utils.log("WARNING", "Enable epel repo failed...",("exec_salt", self))
            comment = 'Enable epel repo failed'
            return (result, comment, str(e))

        utils.log("INFO", "Begin to execute salt state...", ("exec_salt", self))
        for idx, state in enumerate(states):
            utils.log("INFO", "Begin to execute the %dth salt state..." % (idx+1), ("exec_salt", self))
            try:
                # init state
                try:
                    module_list = []
                    for tag in state.keys():
                        module_list += state[tag].keys()

                    utils.log("INFO", "Check module list %s" % str(module_list), ("exec_salt", self))
                    if module_list and any(['npm' in module_list, 'gem' in module_list, 'pip' in module_list]):
                        self._init_state()
                except Exception, e:
                    utils.log("ERROR", "Re-init state exception: %s" % str(e), ("exec_salt", self))
                    pass

                utils.log("INFO", "Begin to execute salt state...", ("exec_salt", self))
                ret = self.state.call_high(state)
            except Exception, e:
                utils.log("ERROR", "Execute salt state %s failed: %s"% (json.dumps(state), str(e)), ("exec_salt", self))
                return (False, "Execute salt state exception", "")

            if ret:
                # parse the ret and return
                utils.log("INFO", json.dumps(ret), ("exec_salt", self))

                # set comment and output log
                require_in_comment = ''
                require_in_log = ''
                for r_tag, r_value in ret.items():
                    if 'result' not in r_value: continue    # filter no result

                    # parse require in result
                    if 'require_in' in r_tag:
                        require_in_comment = '{0}{1}{2}'.format(
                                require_in_comment,
                                '\n\n' if require_in_comment else '',
                                r_value['comment'] if 'comment' in r_value and r_value['comment'] else ''
                            )
                        require_in_log = '{0}{1}{2}'.format(
                                require_in_log,
                                '\n\n' if require_in_log else '',
                                r_value['state_stdout'] if 'state_stdout' in r_value and r_value['state_stdout'] else ''
                            )

                    # parse require result
                    elif 'require' in r_tag:
                        comment = '{0}{1}{2}'.format(
                            r_value['comment'] if 'comment' in r_value and r_value['comment'] else '',
                            '\n\n' if comment else '',
                            comment
                            )
                        out_log = '{0}{1}{2}'.format(
                            r_value['state_stdout'] if 'state_stdout' in r_value and r_value['state_stdout'] else '',
                            '\n\n' if out_log else '',
                            out_log
                            )

                    # parse common result
                    else:
                        comment = '{0}{1}{2}'.format(
                            comment,
                            '\n\n' if comment else '',
                            r_value['comment'] if 'comment' in r_value and r_value['comment'] else ''
                            )
                        out_log = '{0}{1}{2}'.format(
                            out_log,
                            '\n\n' if out_log else '',
                            r_value['state_stdout'] if 'state_stdout' in r_value and r_value['state_stdout'] else ''
                            )

                    result = r_value['result']
                    # break when one state runs failed
                    if not result:
                        break

                # add require in comment and log
                if require_in_comment:
                    comment += '\n\n' + require_in_comment

                if require_in_log:
                    out_log += '\n\n' + require_in_log

            else:
                out_log = "wait failed"

        return (result, comment, out_log)

    def get_mods(self, states):
        """
            Get all modules.
        """
        mods = []

        for state in states:
            for tag, module in state.iteritems():

                mods = list(set(mods + module.keys()))

        return mods

    def _enable_epel(self):
        """
            Install and enbale epel in yum package manager system.
        """
        if self.os_type not in ['centos', 'redhat', 'amazon']:  return

        try:
            epel_rpm = 'epel-release-6-8.noarch.rpm'
            if self.os_type in ['centos', 'redhat'] and self.os_release and float(self.os_release) >= 7.0:
                epel_rpm = 'epel-release-7-0.2.noarch.rpm'
            if not self._pkg_cache.endswith('/'):   self._pkg_cache += '/'
            epel_rpm = self._pkg_cache+epel_rpm
            if not self.__is_existed(epel_rpm):
                utils.log("WARNING", "Cannot find the epel rpm package in %s" % self._pkg_cache, ("_enable_epel", self))
                return

            import subprocess
            if self.os_type in ['centos', 'redhat']:    # install with rpm on centos|redhat
                cmd = 'rpm -ivh ' + epel_rpm + '; yum upgrade -y ca-certificates --disablerepo=epel;'
            else:   # install with yum on amazon ami
                cmd = 'yum -y install epel-release;'

            cmd += 'yum-config-manager --enable epel'

            devnull = open('/dev/null', 'w')
            subprocess.Popen(
                cmd,
                shell=True,
                stdout=devnull,
                stderr=devnull,
                ).wait()
        except Exception, e:
            utils.log("ERROR", str(e), ("_enable_epel", self))
            return

    def __mkdir(self, path):
        """
            Check and make directory.
        """
        if not os.path.isdir(path):
            try:
                os.makedirs(path)
            except OSError, e:
                utils.log("ERROR", "Create directory %s failed" % path, ("__mkdir", self))
                return False

        return True

    def __is_existed(self, files):
        """
            Check files whether existed.
        """
        file_list = []

        if isinstance(files, basestring):
            file_list.append(files)
        elif isinstance(files, list):
            file_list = files
        else:
            utils.log("WARNING", "No input files to check...", ("__is_existed", self))
            return

        the_file = None
        for f in file_list:
            if os.path.isfile(f):
                the_file = f
                break

        if not the_file:
            utils.log("WARNING", "No files in %s existed..." % str(files), ("__is_existed", self))
            return

        return the_file

    def __preinstall_npm(self):
        """
            Preinstall nodejs and npm.
        """

        try:
            if not self.os_type:
                return

            if self.os_type in ['centos', 'redhat', 'amazon']:
                pm = 'yum'
            elif self.os_type in ['debian', 'ubuntu']:
                pm = 'apt-get'
            else:
                utils.log("ERROR", "Not supported os {0}".format(self.os_type), ("__preinstall_npm", self))

            # install nodejs
            import subprocess
            if self.os_type in ['redhat']:
                cmd = '{0} install -y nodejs curl'.format(pm)
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)

                out, err = process.communicate()
                if process.returncode != 0:
                    utils.log("ERROR", "Excute cmd {0} failed: {1}".format(cmd, err), ("__preinstall_npm", self))
                    raise ExecutionException("Excute cmd %s failed"%cmd)

            elif self.os_type in ['debian']:
                cmd = 'echo "deb http://ftp.us.debian.org/debian wheezy-backports main" >> /etc/apt/sources.list && apt-get update && apt-get install -y nodejs-legacy curl'

                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)

                out, err = process.communicate()
                if process.returncode != 0:
                    utils.log("ERROR", "Excute cmd {0} failed: {1}".format(cmd, err), ("__preinstall_npm", self))
                    raise ExecutionException("Excute cmd %s failed"%cmd)

            # install npm
            tmp_dir = '/opt/visualops/tmp'
            cmd = 'curl --insecure https://www.npmjs.org/install.sh | clean=y bash'
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

            out, err = process.communicate()
            if process.returncode != 0:
                utils.log("ERROR", "Excute cmd {0} failed: {1}".format(cmd, err), ("__preinstall_npm", self))
                raise ExecutionException("Excute cmd %s failed"%cmd)
        except Exception, e:
            utils.log("ERROR", str(e), ("__preinstall_npm", self))
            raise ExecutionException("Install npm failed")


# For unit tests only
def main():
        salt_opts = {
                'file_client':       'local',
                'renderer':          'yaml_jinja',
                'failhard':          False,
                'state_top':         'salt://top.sls',
                'nodegroups':        {},
                'file_roots':        '/srv/salt',
                'state_auto_order':  False,
                'extension_modules': '/var/cache/salt/minion/extmods',
                'id':                '',
                'pillar_roots':      '',
                'cachedir':          '/var/cache/visualops/',
                'test':              False,
                }

        states = {
                '_scribe_1_scm_git_git://github.com/facebook/scribe.git_latest' : {
                        "git": [
                                "latest",
                                {
                                        "name": "git://github.com/facebook/scribe.gits",
                                        "rev": "master",
                                        "target": "/visualops/deps/scribe",
                                        "user": "root"
                                }
                        ]
                }
        }

        runner = StateRunner(salt_opts)

        ret = runner.exec_salt(states)

        if ret:
                print json.dumps(ret, sort_keys=True,
                          indent=4, separators=(',', ': '))
        else:
                print "wait failed"

if __name__ == '__main__':
        main()
