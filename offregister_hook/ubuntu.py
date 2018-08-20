import sys
from cStringIO import StringIO
from functools import partial
from json import dump
from os import path

from fabric.contrib.files import upload_template
from fabric.operations import sudo, put, run
from offregister_fab_utils.apt import apt_depends
from offregister_fab_utils.fs import cmd_avail
from offregister_fab_utils.ubuntu.systemd import restart_systemd
from offregister_go import ubuntu as go
from pkg_resources import resource_filename

hook_dir = partial(path.join, path.dirname(resource_filename(sys.modules[__name__].__name__, '__init__.py')), '_conf')


def install_configure0(*args, **kwargs):
    apt_install = False
    if apt_install:
        apt_depends('webhook')
    elif not cmd_avail('webhook'):
        go.install0()
        run('go get github.com/adnanh/webhook')

    if kwargs.get('HOOK_PORT') == 443 or kwargs.get('HOOK_KEY') or kwargs.get('HOOK_CERT'):
        kwargs['HOOK_SECURE'] = ''
    if not kwargs.get('HOOK_IP') and kwargs.get('SERVER_NAME'):
        kwargs['HOOK_IP'] = kwargs['SERVER_NAME']

    if not kwargs.get('HOOK_HOOKS'):
        kwargs['HOOK_HOOKS'] = '/etc/webhook.json'
    else:
        sudo('mkdir -p "${' + kwargs['HOOK_HOOKS'] + '##*/}"', shell_escape=False)

    sio = StringIO()
    dump(kwargs['HOOK_HOOKS_JSON'], sio)
    tmp = '{}.tmp'.format(kwargs['HOOK_HOOKS'])
    put(sio, tmp, use_sudo=True)
    sudo('cat {tmp} | envsubst > {hooks} && rm {tmp}'.format(tmp=tmp, hooks=kwargs['HOOK_HOOKS']))

    if 'HOOK_NOPANIC' not in kwargs:
        kwargs['HOOK_NOPANIC'] = ''  # true
    elif not kwargs['HOOK_NOPANIC']:
        del kwargs['HOOK_NOPANIC']

    upload_template(hook_dir('webhook.service'), '/lib/systemd/system/',
                    context={
                        'CMD': '/usr/bin/webhook' if apt_install else run('echo "$GOPATH/bin/webhook"',
                                                                          quiet=True, shell_escape=False),
                        'ARGS': ' '.join(
                            "-{cli_arg} '{cli_val}'".format(cli_arg=cli_arg,
                                                            cli_val=kwargs['HOOK_{}'.format(cli_arg.upper())]
                                                            )
                            for cli_arg in (
                                'cert', 'header', 'hooks', 'hotreload', 'ip', 'key',
                                'nopanic', 'port', 'secure', 'template', 'verbose'
                            )
                            if 'HOOK_{}'.format(cli_arg.upper()) in kwargs).replace(" ''", '').replace(" 'True'", '')},
                    use_sudo=True)

    return restart_systemd('webhook')
