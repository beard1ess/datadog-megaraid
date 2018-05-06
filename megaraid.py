# Megacli check for datadog
# requires the following line in sudoers

# dd-agent ALL = (root) NOPASSWD: /usr/sbin/megacli

import time
import shlex
import os
import json
import syslog

from subprocess import Popen, PIPE
from hashlib import md5

# project
try:
    from checks import AgentCheck
except ImportError:
    # Dummy class to allow local testing
    class AgentCheck:
        def __init__(self, *args):
            pass

        def gauge(self, data, value, device_name=None, tags=None):
            post = {}
            if device_name is not None:
                post['device'] = device_name
            if tags is not None:
                post['tags'] = device_name
            post[data] = value
            print(json.dumps(post))


class MegaraidCheck(AgentCheck):
    def __init__(self, name, init_config, agentConfig, instances=None):
        AgentCheck.__init__(self, name, init_config, agentConfig, instances)
        # Defaults
        self.LICEXPIRE = 30
        self.MONCOUNT = 100
        self.syslog = syslog.syslog
    pass

    def check(self, instance):
        megacli = '/usr/sbin/megacli'

        if not (os.path.isfile(megacli) and os.access(megacli, os.X_OK)):
            self.syslog("Unable to use megacli at %s" % megacli)
        else:
            self.check_adapter(instance, megacli)
            self.check_disks(instance, megacli)

    def check_adapter(self, instance, megacli):
        adapter = instance['adapter']
        cmd = "sudo %s -LDInfo -Lall -a%s" % (megacli, instance.get('adapter', 0))
        process = Popen(shlex.split(cmd), stdout=PIPE, close_fds=True)
        (output, err) = process.communicate()
        exit_code = process.wait()
        
        adapters = dict()
        if exit_code != 0:
            self.syslog("Got exit code %s for command '%s' and output %s" % (exit_code, cmd, output))
            return

        current_adapter=None

        for line in output.split('\n'):
            if line.startswith('Adapter'):
                current_adapter = line.split(' ')[1]
                adapters['0'] = dict()
            if line.startswith('State'):
                if "Optimal" in line:
                    adapters[current_adapter]['state'] = 0
                else:
                    adapters[current_adapter]['state'] = 1

                self.gauge('megaraid.adapter.status', adapters[current_adapter]['state'], device_name="%s:megaraid/%s" % (self.hostname, current_adapter))

    def check_disks(self, instance, megacli):
        adapter = instance.get('adapter', 0)
        cmd = "sudo %s -pdlist -a%s" % (megacli, adapter)
        process = Popen(shlex.split(cmd), stdout=PIPE, close_fds=True)
        (output, err) = process.communicate()
        exit_code = process.wait()
        
        disks = dict()

        if exit_code != 0:
            self.syslog("Got exit code %s for command '%s' and output %s" % (exit_code, cmd, output))
            return

        current_disk = None

        for line in output.split('\n'):
            if line.startswith('Adapter #'):
                adapter = line.split('#')[1]
                disks[adapter] = dict()
            if line.startswith('Device Id:'):
                current_disk = line.split(' ')[2]
                disks[adapter][current_disk] = dict()
            if line.startswith('Media Error Count'):
                disks[adapter][current_disk]['media_error_count'] = int(line.split(' ')[3])
            elif line.startswith('Other Error Count'):
                disks[adapter][current_disk]['other_error_count'] = int(line.split(' ')[3])
            elif line.startswith('Predictive Failure Count'):
                disks[adapter][current_disk]['predictive_failure_count'] = int(line.split(' ')[3])
            elif line.startswith('Drive has flagged a S.M.A.R.T alert'):
                if "No" in line:
                    disks[adapter][current_disk]['smart_alert'] = 0

                else:
                    disks[adapter][current_disk]['smart_alert'] = 1

            elif line.startswith('Drive Temperature'):
                disks[adapter][current_disk]['temperature'] = int(line.split(':')[1].split('C')[0])
                self.syslog("Got temp %s for disk 'megaraid/%s/%s'" % (disks[adapter][current_disk]['temperature'], adapter, current_disk))
            elif line.startswith('Firmware state'):
                if line.count('Online') < 1 or line.count('Spun Up'):
                    disks[adapter][current_disk]['firmware_ok'] = 0
                else:
                    disks[adapter][current_disk]['firmware_ok'] = 1

        for adapt in disks:
            for disk in disks[adapt]: 
                for key in disks[adapt][disk]: 
                    self.gauge('megaraid.device.%s' % key, disks[adapt][disk][key], device_name="%s:adapter:%s/%s" % (self.hostname, adapt, disk))


if __name__ == '__main__':
    check = MegaraidCheck("foo", "bar", "baz")
    instance = {
        "adapter": "ALL"

    }
    check.check(instance)

