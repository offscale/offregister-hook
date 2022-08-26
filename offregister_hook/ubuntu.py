import sys
from sys import version

if version[0] == "2":
    from cStringIO import StringIO

else:
    from io import StringIO

from functools import partial
from os import path

from nginx_parse_emit.emit import api_proxy_block
from nginx_parse_emit.utils import upsert_by_location, upsert_upload
from nginxparser import dump, loads
from offregister_fab_utils.apt import apt_depends
from offregister_fab_utils.fs import cmd_avail
from offregister_fab_utils.ubuntu.systemd import restart_systemd
from offregister_go import ubuntu as go
from pkg_resources import resource_filename

hook_dir = partial(
    path.join,
    path.dirname(resource_filename(sys.modules[__name__].__name__, "__init__.py")),
    "_conf",
)


def install_configure0(*args, **kwargs):
    apt_install = False
    if apt_install:
        apt_depends(c, "webhook")
    elif not cmd_avail(c, "webhook"):
        go.install0()
        c.run("go get github.com/adnanh/webhook")

    if (
        kwargs.get("HOOK_PORT") == 443
        or kwargs.get("HOOK_KEY")
        or kwargs.get("HOOK_CERT")
    ):
        kwargs["HOOK_SECURE"] = True
    if not kwargs.get("HOOK_IP") and kwargs.get("SERVER_NAME"):
        kwargs["HOOK_IP"] = kwargs["SERVER_NAME"]

    if not kwargs.get("HOOK_HOOKS"):
        kwargs["HOOK_HOOKS"] = "/etc/webhook.json"
    else:
        c.sudo('mkdir -p "${' + kwargs["HOOK_HOOKS"] + '##*/}"', shell_escape=False)

    sio = StringIO()
    dump(kwargs["HOOK_HOOKS_JSON"], sio)
    tmp = "{}.tmp".format(kwargs["HOOK_HOOKS"])
    c.put(sio, tmp, use_sudo=True)
    c.sudo(
        "cat {tmp} | envsubst > {hooks} && rm {tmp}".format(
            tmp=tmp, hooks=kwargs["HOOK_HOOKS"]
        )
    )

    if "HOOK_NOPANIC" not in kwargs:
        kwargs["HOOK_NOPANIC"] = ""  # true
    elif not kwargs["HOOK_NOPANIC"]:
        del kwargs["HOOK_NOPANIC"]

    upload_template_fmt(
        c,
        hook_dir("webhook.service"),
        "/lib/systemd/system/",
        context={
            "CMD": "/usr/bin/webhook"
            if apt_install
            else c.run(
                'echo "$GOPATH/bin/webhook"', hide=True, shell_escape=False
            ).stdout.rstrip(),
            "ARGS": " ".join(
                "-{cli_arg} '{cli_val}'".format(
                    cli_arg=cli_arg, cli_val=kwargs["HOOK_{}".format(cli_arg.upper())]
                )
                for cli_arg in (
                    "cert",
                    "header",
                    "hooks",
                    "hotreload",
                    "ip",
                    "key",
                    "nopanic",
                    "port",
                    "secure",
                    "template",
                    "verbose",
                )
                if "HOOK_{}".format(cli_arg.upper()) in kwargs
            )
            .replace(" ''", "")
            .replace(" 'True'", ""),
        },
        use_sudo=True,
    )
    return restart_systemd("webhook")


def configure_nginx1(*args, **kwargs):
    new_conf = lambda orig_conf: upsert_by_location(
        "/hooks",
        orig_conf,
        loads(
            api_proxy_block(
                "/hooks",
                "{protocol}://{host}:{port}/{urlprefix}".format(
                    protocol="https" if kwargs.get("HOOK_SECURE") else "http",
                    host=kwargs.get("HOOK_IP", "0.0.0.0"),
                    port=kwargs.get("HOOK_PORT", 9000),
                    urlprefix=kwargs.get("HOOK_URLPREFIX", "hooks"),
                ),
            )
        ),
    )
    upsert_upload(new_conf, name="hook")
    return restart_systemd("nginx")
