import asyncio
import binascii
import time

import machine
import network
from microdot import Microdot, Response
from microdot.utemplate import Template

import tools


# Netzwerkeinstellungen für LAN mit DHCP konfigurieren (siehe nächster Abschnitt)
def setup_lan():
    hostname = tools.config.get('hostname')
    network.hostname(hostname)
    lan = network.LAN(mdc=machine.Pin(23), mdio=machine.Pin(18), power=machine.Pin(12), phy_type=network.PHY_LAN8720, phy_addr=0)
    lan.active(True)
    # lan.ifconfig('dhcp')
    print('Warte auf Netzwerkverbindung...')
    for _i in range(10):
        if lan.isconnected():
            break
        time.sleep(1)
    if lan.isconnected():
        print('Verbunden! IP-Adresse:', lan.ifconfig()[0])
    else:
        print('Keine Netzverbindung!')


app = Microdot()
Response.default_content_type = 'text/html'


# Hilfsfunktion für Basic Authentication
def check_basic_auth(request):
    auth = request.headers.get('Authorization')
    if not auth:
        return False

    # Erwartet "Basic <base64-encoded username:password>"
    try:
        auth_type, credentials = auth.split(' ', 1)
        if auth_type.lower() != 'basic':
            return False

        # Base64-Dekodierung der Anmeldeinformationen
        decoded_credentials = binascii.a2b_base64(credentials).decode('utf-8')
        username, password = decoded_credentials.split(':', 1)

        return username == tools.config.get('username') and password == tools.config.get('password')
    except Exception:
        return False


# Authentifizierungs-Wrapper für geschützte Routen
def requires_auth(handler):
    async def wrapper(request, *args, **kwargs):
        if not check_basic_auth(request):
            return Response(status_code=401, headers={'WWW-Authenticate': 'Basic realm="Authentication Required"'}, body='Unauthorized')
        return await handler(request, *args, **kwargs)

    return wrapper


@app.route('/test')
@requires_auth
async def index(request):
    print('/test GET')
    return Template('dummy.html').render(name='user')


@app.route('/')
@requires_auth
async def index(request):
    print('/ GET')

    # read registered tag information and convert the UID to a string
    store = tools.AuthorizedRFIDStore()
    tags = [[tools.uid2str(i[0])] + i[1:] for i in store.get_all()]
    print(tags)

    # render the HTML page
    return Template('main.html').render(tags=tags)


@app.route('/tag')
@requires_auth
async def get_tag(request):
    print('/tag GET')

    data = None
    try:
        data = await tools.read_data(n_trials=20)
    except tools.RFIDException as e:
        print(f'Failed to read the RFID tag: {e}\n')

    if data:
        return data, 200
    return {}, 400


@app.put('/tags')
@requires_auth
async def add_tag(request):
    print('/tags PUT')
    new_tag = request.json
    print(f'  {new_tag}')

    if 'username' in new_tag and 'timestamp' in new_tag and 'collmex_id' in new_tag and 'password' in new_tag:
        # prepare the flags parameter
        has_cash_register_access = new_tag.get('hasCashRegisterAccess') in {True, 'true', 'True', 'TRUE'}
        flags = 0
        if has_cash_register_access:
            flags |= tools.FLAG_CASH_REGISTER

        async with tools.reader_lock:
            # get the UID
            uid = await tools.read_uid(unlocked=True)

            print(f'  UID: {uid}')
            if uid is None:
                return {'success': False}, 400
            try:
                store = tools.AuthorizedRFIDStore()
                if store.is_uid_registered(uid):
                    uid_str = tools.uid2str(uid)
                    msg = f'UID {uid_str} has already been registered!'
                    raise ValueError(msg)
                store.add(uid, new_tag['username'], new_tag['collmex_id'], new_tag['timestamp'])
                print('  setting custom key..')
                await tools.set_key_for_all_sectors(tools.CUSTOM_KEY, uid=uid, unlocked=True)
                print('  writing data to rfid tag..')
                await tools.write_data(new_tag['username'], new_tag['collmex_id'], new_tag['password'], flags=flags, uid=uid, unlocked=True)
                print('  success :)')
                return {'success': True}, 200
            except (tools.RFIDException, ValueError) as exc:
                print('  failure :(')
                print(exc)
                return {'success': False, 'msg': str(exc)}, 400
    else:
        return {'success': False, 'msg': 'Not all values have been specified!'}, 400


@app.delete('/tags')
@requires_auth
async def delete_tag(request):
    print('/tags DELETE')
    params = request.args
    print(f'  {params}')

    try:
        async with tools.reader_lock:
            if 'uid' in params:
                uid = tools.hexstr2values(params['uid'])
            else:
                uid = await tools.read_uid(unlocked=True)

            if 'reset' in params and params['reset'].lower() == 'true':
                print('  deleting all sectors..')
                await tools.write_data('', '', '', meta_data='', uid=uid, unlocked=True)
                print('  setting default key..')
                await tools.set_key_for_all_sectors(tools.DEFAULT_KEY, uid=uid, unlocked=True)

            store = tools.AuthorizedRFIDStore()
            store.remove(uid)

            print('  success :)')
            return {'success': True}, 200
    except tools.RFIDException as exc:
        print('  failure :(')
        print(exc)
        return {'success': False, 'msg': str(exc)}, 400


async def _start_web_server():
    print('Starting web server...')
    # app.run(port=80)
    await app.start_server(debug=False, port=80)


def start_web_server():
    loop = asyncio.get_event_loop()
    loop.create_task(_start_web_server())
    loop.run_forever()


def main():
    # Rufe setup_lan auf, um das LAN mit DHCP zu aktivieren
    setup_lan()

    print('Starting RFID reading...')
    tools.start_rfid_reading()

    # do not start the web server if the OLIMEX button has been pressed
    button_pin = machine.Pin(34, machine.Pin.IN)
    time.sleep(0.1)
    if button_pin.value() == 0:
        print('Debug mode: Button pressed, web server will NOT start.')
    else:
        start_web_server()


if __name__ == '__main__':
    main()
