import logging
import os
import requests

from flask import \
    Flask, \
    jsonify, \
    make_response, \
    redirect, \
    request, \
    send_from_directory

import src.config as cfg
from src.emotion_client import EmotionClient
from src.spotify_client import SpotifyClient
from src.spotify_oauth import SpotifyOAuth
from src.utils import exists

app = Flask(__name__, static_folder='static')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IS_PRODUCTION = bool(os.environ.get('IS_PRODUCTION', default=False))
APP_BASE_URL = 'TODO' if IS_PRODUCTION else 'http://0.0.0.0:3000'


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def _proxy(path):
    logger.info("/proxy called with /%s" % path)

    valid_paths = ['', 'mix']

    if path not in valid_paths:
        return redirect('%s/app/%s' % (APP_BASE_URL, '404'))

    # TODO: Verify that token exists, otherwise redirect to login and then
    #       redirect to wanted path
    return redirect('%s/app/%s' % (APP_BASE_URL, path))


@app.route('/login', methods=['GET'])
def _login():
    logger.info('/login called')
    sp = _spotify_oauth()

    cookie_token = _get_token(request)
    if exists(cookie_token):
        logger.info('Token found')

        current_token = sp.cookie_to_dict(cookie_token)
        if sp.is_token_expired(current_token):
            logger.info('Token is expired - requesting new token')
            refresh_token = sp.refresh_token(current_token)
            refresh_token['refresh_token'] = current_token['refresh_token']
            current_token = refresh_token

        logger.info('Redirecting to /mix')
        response = make_response(redirect('/mix'))
        cookie = sp.json_to_cookie(current_token)
        logger.info('Setting token as cookie: %s' % cookie)
        response.set_cookie('spotify_token', cookie)

        return response
    else:
        logger.info('No token found - getting one')
        return redirect(sp.get_auth_url(), code=302)


@app.route('/callback', methods=['GET'])
def _callback():
    logger.info('/callback called')
    sp = _spotify_oauth()

    token = sp.get_new_token(request)

    response = make_response(redirect('%s/app/mix' % APP_BASE_URL))
    cookie = sp.json_to_cookie(token)
    logger.info('Setting token as cookie: %s' % cookie)
    response.set_cookie('spotify_token', cookie)

    return response


@app.route('/v1/user', methods=['GET'])
def _user():
    logger.info('/v1/user called')

    # For now, assume we always have token
    client = _spotify_client(_get_token(request))
    response = client.get_user()

    return jsonify({
        'user': response,
    })


# @app.route('/v1/tracks', methods=['POST'])
# def _tracks():
#     logger.info('/v1/tracks called')
#
#     # TODO: Move validation downstream?
#     if 'face_image' not in request.files:
#         abort(400, 'No file with name \'face_image\' sent')  # Bad request
#     else:
#         image = request.files['face_image']
#         if image and allowed_file_type(image.filename):
#             tracks = spotify_client.get_personalised_tracks(
#                 emotion_client.get_emotions(image.read()), limit=5)
#             return jsonify({
#                 'tracks': tracks
#             })
#         else:
#             abort(400, 'Image extension not allowed')  # Bad request


@app.route('/robots.txt')
@app.route('/sitemap.xml')
def _robots():
    return send_from_directory(app.static_folder, request.path[1:])


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(500)
@app.errorhandler(502)
def _handle_error(error):
    return make_response(jsonify({
        'error_msg': error.description,
        'error_code': int(error.code),
    }), error.code)


# TODO: Move these to util file,
# this file should be clean

def _get_token(req) -> str:
    return req.cookies.get('spotify_token')


def _spotify_oauth() -> SpotifyOAuth:
    c = cfg.spotify_api()
    redirect_uri = '%s/callback' % \
                   ('https://musicify.herokuapp.com' if IS_PRODUCTION
                    else 'http://0.0.0.0:8000')
    state = 'TODO'
    scope = 'user-read-private'
    return SpotifyOAuth(
        requests,  # Pass in the external library
        client_id=c['client_id'],
        client_secret=c['client_secret'],
        redirect_uri=redirect_uri,
        state=state,
        scope=scope
    )


def _spotify_client(token) -> SpotifyClient:
    return SpotifyClient(
        requests,
        _emotion_client(),
        token)


def _emotion_client() -> EmotionClient:
    c = cfg.face_api()
    return EmotionClient(requests, c['subscription_key'])


if __name__ == '__main__':
    # Flask server is only used during development
    if not IS_PRODUCTION:
        app.run(debug=True, host='localhost', port=8000)
