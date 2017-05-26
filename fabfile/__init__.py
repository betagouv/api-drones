from hashlib import md5
from pathlib import Path

from invoke import task


def as_user(ctx, user, cmd, *args, **kwargs):
    ctx.run('sudo --set-home --preserve-env --user {} '
            '{}'.format(user, cmd), *args, **kwargs)


def as_suav(ctx, cmd, *args, **kwargs):
    env = {'FLASK_APP': '/srv/suav/src/suav/__init__.py'}
    env.update(ctx.config.get('env', {}))
    as_user(ctx, 'suav', cmd, env=env)


def sudo_put(ctx, local, remote, chown=None):
    tmp = str(Path('/tmp') / md5(remote.encode()).hexdigest())
    ctx.put(local, tmp)
    ctx.run('sudo mv {} {}'.format(tmp, remote))
    if chown:
        ctx.run('sudo chown {} {}'.format(chown, remote))


@task
def cli(ctx, cmd):
    as_suav(ctx, '/srv/suav/venv/bin/flask {}'.format(cmd))


@task
def system(ctx):
    ctx.run('sudo apt update')
    ctx.run('sudo apt install redis-server python3 python3-dev '
            'python-virtualenv build-essential git wget uwsgi '
            'uwsgi-plugin-python3 bzip2 nginx --yes')
    ctx.run('sudo useradd -N suav -m -d /srv/suav/ || exit 0')
    ctx.run('sudo chown suav:users /var/log/suav')
    ctx.run('sudo chsh -s /bin/bash suav')
    # Allow FLASK_APP env var to be passed through ssh.
    ctx.run('grep -q -r "^AcceptEnv FLASK_APP *" /etc/ssh/sshd_config '
            '|| echo "AcceptEnv FLASK_APP *" '
            '| sudo tee --append /etc/ssh/sshd_config')
    ctx.run('sudo systemctl restart sshd')


@task
def venv(ctx):
    as_suav(ctx, 'virtualenv /srv/suav/venv --python=python3')
    as_suav(ctx, '/srv/suav/venv/bin/pip install pip -U')


@task
def settings(ctx):
    if ctx.settings:
        sudo_put(ctx, ctx.settings, '/etc/default/suav', chown='suav:users')


@task
def http(ctx):
    sudo_put(ctx, 'fabfile/uwsgi_params', '/srv/suav/uwsgi_params')
    sudo_put(ctx, 'fabfile/uwsgi.ini', '/etc/uwsgi/apps-enabled/suav.ini')
    sudo_put(ctx, 'fabfile/nginx.conf', '/etc/nginx/sites-enabled/suav')
    restart(ctx)


@task
def bootstrap(ctx):
    system(ctx)
    venv(ctx)
    settings(ctx)
    http(ctx)


def write_default(ctx):
    content = '\n'.join(['{}={}'.format(k, v)
                         for k, v in ctx.config.get('env', {}).items()])
    ctx.run('echo "{}" | sudo tee /etc/default/suav'.format(content))


@task
def deploy(ctx):
    cli(ctx, 'initdb')
    cmd = '/srv/suav/venv/bin/pip install git+https://github.com/etalab/api-drones --upgrade'
    restart(ctx)


@task
def restart(ctx):
    ctx.run('sudo systemctl restart uwsgi')
    ctx.run('sudo systemctl restart nginx')
