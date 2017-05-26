import json
from datetime import datetime
import os
import uuid

import click
from flask import (Flask, abort, redirect, render_template, request, session,
                   url_for)
from flask_oauthlib.client import OAuth
import peewee
from redis import StrictRedis
from werkzeug import security

get_env = os.environ.get

app = Flask(__name__)
app.config.update(
    SECRET_KEY=get_env('SECRET_KEY', 'sikr3t'),
    FRANCECONNECT_CONSUMER_KEY=get_env('FRANCECONNECT_CONSUMER_KEY', ''),
    FRANCECONNECT_CONSUMER_SECRET=get_env('FRANCECONNECT_CONSUMER_SECRET', ''),
)
oauth = OAuth(app)
DB = StrictRedis(db=7)

db = peewee.SqliteDatabase(get_env('DB_PATH', 'suav.db'))


class Owner(peewee.Model):
    username = peewee.CharField(unique=True)
    fullname = peewee.CharField()

    class Meta:
        database = db


class UAV(peewee.Model):
    name = peewee.CharField(null=False)
    owner = peewee.ForeignKeyField(Owner, related_name='uavs')
    manufacturer = peewee.CharField()
    model = peewee.CharField()
    weight = peewee.IntegerField()
    licence = peewee.CharField()

    class Meta:
        database = db

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.licence:
            self.licence = uuid.uuid4().hex
        return super().save(*args, **kwargs)


@app.route('/')
def home():
    if 'username' in session:
        try:
            Owner.get(Owner.username == session['username'])
        except peewee.DoesNotExist:
            del session['fullname']
    return render_template('home.html')


@app.route('/put', methods=['PUT'])
def put():
    body = json.loads(request.stream.read().decode('utf-8'))
    id_ = body.get('id')
    lon = body.get('lon')
    lat = body.get('lat')
    alt = body.get('alt')
    if not all([id_, lon, lat, alt]):
        abort(400)
    # Only save one position per id.
    DB.geoadd('positions', lon, lat, id_)
    DB.hmset(id_, body)
    id_ = 'p|' + id_ + str(datetime.now().timestamp())
    # Save all position.
    DB.geoadd('history', lon, lat, id_)
    return ''


@app.route('/positions')
def positions():

    def load(k):
        data = {k.decode(): v.decode() for k, v in DB.hgetall(k).items()}
        return {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [data['lon'], data['lat'], data['alt']]
            },
            'properties': {
                'id': data['id'],
                'height': data.get('height')
            }
        }

    keys = DB.zrange('positions', 0, -1)
    return json.dumps([load(k) for k in keys])


@app.route('/map')
def map():
    return render_template('map.html')


@app.route('/immatriculation', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        for key, value in request.form.items():
            if not value:
                break
        else:
            owner = Owner.get(Owner.username == session['username'])
            data = dict(request.form.to_dict())
            data['owner'] = owner
            UAV.create(**data)
        return redirect(url_for('myuav'))
    return render_template('register.html')


@app.route('/mes-drones')
def myuav():
    owner = Owner.get(Owner.username == session['username'])
    uavs = UAV.select().filter(UAV.owner == owner)
    return render_template('myuav.html', uavs=uavs)


@app.route('/tous-les-drones')
def alluav():
    uavs = UAV.select()
    return render_template('alluav.html', uavs=uavs)


fc = oauth.remote_app(
    'franceconnect',
    base_url='https://fcp.integ01.dev-franceconnect.fr/api/v1/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://fcp.integ01.dev-franceconnect.fr/api/v1/token',
    authorize_url='https://fcp.integ01.dev-franceconnect.fr/api/v1/authorize',
    app_key='FRANCECONNECT',
    request_token_params={'scope': 'openid profile'}
)


@fc.tokengetter
def get_oauth_token():
    return session.get('oauth_token')


@app.route('/login/')
@app.route('/login/<provider>/')
def login(provider=None):
    if not provider:
        return render_template('login.html')
    if provider == 'demo':
        try:
            Owner.create(fullname="demo", username="demo")
        except peewee.IntegrityError:
            pass
        session['username'] = "demo"
        session['fullname'] = "demo"
        return redirect(url_for('home'))
    return fc.authorize(
        callback=url_for('authorized', provider='france-connect', _external=True),
        state=security.gen_salt(10),
        nonce=security.gen_salt(10),
    )


@app.route('/logout/')
def logout():
    session.pop('oauth_token', None)
    session.pop('username', None)
    session.pop('fullname', None)
    fc = session.pop('auth_provider', None)
    if fc:
        return redirect('{}logout'.format(fc.base_url))
    return redirect('/')

def get_fc_user_details(data):
    return {
        'username': data['sub'],
        'fullname': ' '.join([data['given_name'], data['family_name']])
    }


@app.route('/authorized/<provider>/')
def authorized(provider):
    token_key = "access_token"
    remote_app = fc
    endpoint = 'userinfo?schema=openid'
    getter = get_fc_user_details
    resp = remote_app.authorized_response()
    if resp is None:
        return 'Access denied: reason=%s error=%s' % (
            request.args['error_reason'],
            request.args['error_description']
        )
    session['oauth_token'] = (resp[token_key],
                              resp.get('oauth_token_secret', ''))  # Oauth1
    session['auth_provider'] = fc
    data = getter(remote_app.get(endpoint).data)
    session['username'] = data['username']
    session['fullname'] = data['fullname']
    return render_template('ajax_authentication_redirect.html',
                           session=session)


@app.cli.command()
def initdb():
    """Initialize the database."""
    click.echo('Init the db')
    db.create_tables([Owner, UAV])
