import network
import time
import tools
import machine
import binascii


# Netzwerkeinstellungen für LAN mit DHCP konfigurieren (siehe nächster Abschnitt)
def setup_lan():
    network.hostname("mio-cash-register")
    lan = network.LAN(mdc=machine.Pin(23), mdio=machine.Pin(18), power=machine.Pin(12), phy_type=network.PHY_LAN8720, phy_addr=0)
    lan.active(True)
    # lan.ifconfig('dhcp')
    print("Warte auf Netzwerkverbindung...")
    for i in range(10):
        if lan.isconnected():
            break
        time.sleep(1)
    if lan.isconnected():
        print("Verbunden! IP-Adresse:", lan.ifconfig()[0])
    else:
        print("Keine Netzverbindung!")


from microdot import Microdot, Response
from microdot.utemplate import Template

app = Microdot()
Response.default_content_type = 'text/html'
USERNAME, PASSWORD = tools.load_credentials()


# Hilfsfunktion für Basic Authentication
def check_basic_auth(request):
    auth = request.headers.get('Authorization')
    if not auth:
        return False

    # Erwartet "Basic <base64-encoded username:password>"
    try:
        auth_type, credentials = auth.split(" " , 1)
        if auth_type.lower() != "basic":
            return False

        # Base64-Dekodierung der Anmeldeinformationen
        decoded_credentials = binascii.a2b_base64(credentials).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)

        return username == USERNAME and password == PASSWORD
    except Exception:
        return False


# Authentifizierungs-Wrapper für geschützte Routen
def requires_auth(handler):
    async def wrapper(request, *args, **kwargs):
        if not check_basic_auth(request):
            return Response(status_code=401, headers={
                'WWW-Authenticate': 'Basic realm="Authentication Required"'
            }, body="Unauthorized")
        return await handler(request, *args, **kwargs)
    return wrapper


@app.route('/test')
@requires_auth
async def index(request):
    print('/test GET')
    return Template("dummy.html").render(name='Alex')


@app.route('/')
@requires_auth
async def index(request):
    print('/ GET')
    tags = tools.load_authorized_uids()
    print(tags)
    return Template("main.html").render(tags=tags)


@app.put('/tags')
@requires_auth
async def add_tag(request):
    print('/tags PUT')
    new_tag = request.json
    print('  {}'.format(new_tag))

    if 'username' in new_tag and 'timestamp' in new_tag:
        with tools.disable_opening_cash_register():
            uid = await tools.read_uid()
        if uid is None:
            return {'success': False}, 400
        else:
            tools.add_uid(uid, new_tag['username'], new_tag['timestamp'])
            return {'success': True}, 200
    else:
        return {'success': False}, 400


@app.delete('/tags')
@requires_auth
async def delete_tag(request):
    print('/tags DELETE')
    params = request.args
    print('  {}'.format(params))

    if 'uid' in params:
        tools.remove_uid(params['uid'])
        return {'success': True}, 200
    else:
        return {'success': False}, 400


if __name__ == '__main__':
    # Rufe setup_lan auf, um das LAN mit DHCP zu aktivieren
    setup_lan()

    print("Starting RFID reading...")
    tools.start_rfid_reading()

    print("Starting web server...")
    app.run(port=80)
