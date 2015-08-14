# -*- coding: utf-8 -*-
'''
An engine that reads messages from the redis sentinel pubsub and sends reactor
events based on the channels they are subscribed to.

.. versionadded: Boron

:configuration:

    Example configuration
        engines:
          - redis_sentinel:
              hosts:
                matching: 'board*'
                port: 26379
                interface: eth2
              channels:
                - '+switch-master'
                - '+odown'
                - '-odown'

:depends: redis
'''
import redis
import threading
import salt.client

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

import logging
log = logging.getLogger(__name__)
log.debug('LOAD REDIS_SENTINEL')


def __virtual__():
    return HAS_REDIS


class Listener(object):
    def __init__(self, host=None, port=None, channels=None, tag=None):
        if host is None:
            host = 'localhost'
        if port is None:
            port = 26379
        if channels is None:
            channels = ['*']
        if tag is None:
            tag = 'salt/engine/redis_sentinel'
        super(Listener, self).__init__()
        self.tag = tag
        self.redis = redis.StrictRedis(host=host, port=port)
        self.pubsub = self.redis.pubsub()
        self.pubsub.psubscribe(channels)
        self.fire_master = salt.utils.event.get_master_event(__opts__, __opts__['sock_dir']).fire_event

    def work(self, item):
        ret = {'channel': item['channel']}
        if isinstance(item['data'], (int, long)):
            ret['code'] = item['data']
        elif item['channel'] == '+switch-master':
            ret.update(dict(zip(('master', 'old_host', 'old_port', 'new_host', 'new_port'), item['data'].split(' '))))
        elif item['channel'] in ('+odown', '-odown'):
            ret.update(dict(zip(('master', 'host', 'port'), item['data'].split(' ')[1:])))
        else:
            ret = {
                'channel': item['channel'],
                'data': item['data'],
            }
        self.fire_master(ret, '{0}/{1}'.format(self.tag, item['channel']))

    def run(self):
        log.debug('Start Listener')
        for item in self.pubsub.listen():
            log.debug('Item: \n{0}'.format(item))
            self.work(item)


def start(hosts, channels, tag=None):
    if tag is None:
        tag = 'salt/engine/redis_sentinel'
    local = salt.client.LocalClient()
    ips = local.cmd(hosts['matching'], 'network.ip_addrs', [hosts['interface']]).values()
    client = Listener(host=ips.pop()[0], port=hosts['port'], channels=channels, tag=tag)
    client.run()
